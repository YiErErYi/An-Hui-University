import sys
import time
import pyautogui
import pyperclip
import json
import threading
import gc
import os
import glob
import datetime
from pynput import mouse, keyboard
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QComboBox, QTextEdit, QSpinBox,
    QMessageBox, QListWidget, QListWidgetItem, QInputDialog, QFileDialog
)
from PyQt5.QtCore import pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QKeyEvent

# 禁用pyautogui的failsafe机制，防止程序意外退出
pyautogui.FAILSAFE = False


class AutoMouseKeyboard(QWidget):
    log_signal = pyqtSignal(str)
    
    def __init__(self):
        try:
            print("初始化 AutoMouseKeyboard...")
            super().__init__()
            self.workflow = []  # 存储操作步骤
            self.recording = False
            self.recorded_events = []
            self.current_history_json = None  # 当前选中的历史json文件
            self.replaying = False  # 添加回放状态标志
            self.replay_thread = None  # 添加回放线程引用
            print("开始初始化 UI...")
            self.init_ui()
            print("UI 初始化完成，连接信号...")
            self.log_signal.connect(self.log_msg)
            print("AutoMouseKeyboard 初始化完成")
        except Exception as e:
            print(f"AutoMouseKeyboard 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def init_ui(self):
        self.setWindowTitle('自动键鼠操作增强版')
        self.setGeometry(600, 300, 600, 700)  # 增大窗口以适应更多控件

        self.label = QLabel('设置参数后点击按钮自动执行操作', self)
        self.log = QTextEdit(self)
        self.log.setReadOnly(True)

        # 坐标输入
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel('X:'))
        self.x_input = QLineEdit('500')
        coord_layout.addWidget(self.x_input)
        coord_layout.addWidget(QLabel('Y:'))
        self.y_input = QLineEdit('300')
        coord_layout.addWidget(self.y_input)
        self.coord_display = QLabel('当前鼠标坐标：(0, 0)')
        coord_layout.addWidget(self.coord_display)

        # 鼠标操作选择
        self.mouse_action = QComboBox()
        self.mouse_action.addItems(['移动', '单击', '双击', '右击', '拖动'])

        # 键盘输入
        kb_layout = QHBoxLayout()
        kb_layout.addWidget(QLabel('键盘输入:'))
        self.kb_input = QLineEdit('Hello, 自动化!')
        kb_layout.addWidget(self.kb_input)

        # 延迟设置
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel('延迟(秒):'))
        self.delay_input = QSpinBox()
        self.delay_input.setRange(0, 30)
        self.delay_input.setValue(3)
        delay_layout.addWidget(self.delay_input)

        # 按钮
        self.btn = QPushButton('开始自动操作', self)
        self.btn.clicked.connect(self.run_automation)

        # 录制按钮
        self.record_btn = QPushButton('开始录制用户操作')
        self.record_btn.setCheckable(True)
        self.record_btn.clicked.connect(self.toggle_recording)

        # 回放录制操作按钮
        self.replay_btn = QPushButton('回放录制操作')
        self.replay_btn.clicked.connect(self.replay_recorded_events)

        # 工作流操作区
        self.workflow_list = QListWidget()
        self.add_step_btn = QPushButton('添加步骤')
        self.del_step_btn = QPushButton('删除选中步骤')
        self.run_workflow_btn = QPushButton('执行全部步骤')
        self.save_workflow_btn = QPushButton('保存为历史记录')  # 新增按钮
        
        self.add_step_btn.clicked.connect(self.add_step)
        self.del_step_btn.clicked.connect(self.del_step)
        self.run_workflow_btn.clicked.connect(self.run_workflow)
        self.save_workflow_btn.clicked.connect(self.save_workflow_as_history) # 连接保存方法

        # 历史记录区
        self.history_list = QListWidget()
        self.rename_history_btn = QPushButton('重命名')
        self.delete_history_btn = QPushButton('删除')
        
        self.rename_history_btn.clicked.connect(self.rename_history_record)
        self.delete_history_btn.clicked.connect(self.delete_history_record)

        # 创建主布局
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addLayout(coord_layout)
        layout.addWidget(self.mouse_action)
        layout.addLayout(kb_layout)
        layout.addLayout(delay_layout)
        layout.addWidget(self.btn)
        layout.addWidget(QLabel('操作日志:'))
        layout.addWidget(self.log)
        layout.addWidget(QLabel('自定义工作流:'))
        layout.addWidget(self.workflow_list)
        
        btns_layout = QHBoxLayout()
        btns_layout.addWidget(self.add_step_btn)
        btns_layout.addWidget(self.del_step_btn)
        btns_layout.addWidget(self.run_workflow_btn)
        btns_layout.addWidget(self.save_workflow_btn)
        layout.addLayout(btns_layout)
        
        layout.addWidget(self.record_btn)
        layout.addWidget(self.replay_btn)
        layout.addWidget(QLabel('历史操作记录:'))
        layout.addWidget(self.history_list)
        
        history_btns_layout = QHBoxLayout()
        history_btns_layout.addWidget(self.rename_history_btn)
        history_btns_layout.addWidget(self.delete_history_btn)
        layout.addLayout(history_btns_layout)
        
        # 添加快捷键提示
        shortcut_label = QLabel('快捷键: Del键-删除历史记录, Esc键-中断录制/回放')
        shortcut_label.setStyleSheet('color: gray; font-size: 9px;')
        layout.addWidget(shortcut_label)
        self.setLayout(layout)
        self.coord_timer = self.startTimer(100)  # 100ms刷新一次
        self.refresh_history_list()
        # 连接历史记录点击事件
        self.history_list.itemClicked.connect(self.on_history_item_clicked)
        # 设置焦点策略以接收键盘事件
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()
    
    def keyPressEvent(self, a0: QKeyEvent):
        """处理键盘按键事件"""
        # Del键删除选中的历史记录
        if a0.key() == 16777223:  # Qt.Key_Delete
            if self.history_list.hasFocus() or self.history_list.currentItem():
                self.delete_history_record()
                return
        # Esc键中断录制和回放
        elif a0.key() == 16777216:  # Qt.Key_Escape
            if self.recording:
                self.log_msg("用户按下Esc键，中断录制...")
                self.toggle_recording()
                return
            elif self.replaying:
                self.log_msg("用户按下Esc键，中断回放...")
                self.stop_replay()
                return
        
        # 调用父类的事件处理
        super().keyPressEvent(a0)

    def stop_replay(self):
        """停止回放操作"""
        if self.replaying and self.replay_thread:
            self.replaying = False
            try:
                # 等待回放线程结束（最多等待2秒）
                if self.replay_thread.is_alive():
                    self.replay_thread.join(timeout=2)
                self.log_msg("回放已被用户中断")
            except Exception as e:
                self.log_msg(f"停止回放时出错: {e}")
            finally:
                self.replay_thread = None

    def log_msg(self, msg):
        """添加日志消息"""
        self.log.append(msg)
        QApplication.processEvents()

    def run_automation(self):
        """执行单次自动操作"""
        try:
            x = int(self.x_input.text())
            y = int(self.y_input.text())
            action = self.mouse_action.currentText()
            kb_text = self.kb_input.text()
            delay = self.delay_input.value()
            self.label.setText(f'{delay}秒后开始，请切换到目标窗口...')
            self.log_msg(f'等待{delay}秒...')
            QApplication.processEvents()
            time.sleep(delay)
            if action == '移动':
                pyautogui.moveTo(x, y, duration=1)
                self.log_msg(f'鼠标移动到({x},{y})')
            elif action == '单击':
                pyautogui.moveTo(x, y, duration=1)
                pyautogui.click()
                self.log_msg(f'鼠标单击({x},{y})')
            elif action == '双击':
                pyautogui.moveTo(x, y, duration=1)
                pyautogui.doubleClick()
                self.log_msg(f'鼠标双击({x},{y})')
            elif action == '右击':
                pyautogui.moveTo(x, y, duration=1)
                pyautogui.rightClick()
                self.log_msg(f'鼠标右击({x},{y})')
            elif action == '拖动':
                pyautogui.moveTo(x, y, duration=1)
                pyautogui.dragRel(100, 0, duration=1)
                self.log_msg(f'鼠标从({x},{y})向右拖动100像素')
            if kb_text.strip():
                pyperclip.copy(kb_text)
                pyautogui.hotkey('ctrl', 'v')
                pyautogui.press('enter')
                self.log_msg(f'键盘输入: {kb_text}')
            self.label.setText('操作已完成！')
            self.log_msg('操作已完成！')
        except Exception as e:
            self.log_msg(f'发生错误: {e}')
            self.label.setText('发生错误！')

    def timerEvent(self, a0):
        """更新鼠标坐标显示"""
        try:
            x, y = pyautogui.position()
            self.coord_display.setText(f'当前鼠标坐标：({x}, {y})')
        except Exception:
            pass

    def add_step(self):
        """添加步骤到自定义工作流"""
        # 弹窗选择操作类型
        actions = ['移动', '单击', '双击', '右击', '拖动', '键盘输入', '延迟', '热键']
        action, ok = QInputDialog.getItem(self, '选择操作', '操作类型：', actions, 0, False)
        if not ok:
            return
        # 根据类型输入参数
        if action in ['移动', '单击', '双击', '右击', '拖动']:
            x, ok1 = QInputDialog.getInt(self, '参数', 'X坐标：', 500)
            if not ok1: return
            y, ok2 = QInputDialog.getInt(self, '参数', 'Y坐标：', 300)
            if not ok2: return
            if action == '拖动':
                dx, ok3 = QInputDialog.getInt(self, '参数', '水平拖动距离(px)：', 100)
                if not ok3: return
                step = {'type': action, 'x': x, 'y': y, 'dx': dx}
                desc = f'{action}到({x},{y})，水平拖动{dx}px'
            else:
                step = {'type': action, 'x': x, 'y': y}
                desc = f'{action}到({x},{y})'
        elif action == '键盘输入':
            text, ok = QInputDialog.getText(self, '参数', '输入内容：', text='Hello, 自动化!')
            if not ok: return
            step = {'type': action, 'text': text}
            desc = f'键盘输入: {text}'
        elif action == '延迟':
            sec, ok = QInputDialog.getInt(self, '参数', '延迟秒数：', 1)
            if not ok: return
            step = {'type': action, 'sec': sec}
            desc = f'延迟{sec}秒'
        elif action == '热键':
            hotkeys = [
                'Ctrl+C 复制', 'Ctrl+V 粘贴', 'Ctrl+X 剪切', 'Ctrl+Z 撤销', 'Ctrl+Y 重做',
                'Ctrl+A 全选', 'Alt+Tab 切换窗口', 'Win+D 显示桌面', 'F5 刷新',
                'Delete 删除', 'Insert 插入', 'Home 首位', 'End 末位',
                'PageUp 上翻页', 'PageDown 下翻页', 'Enter 回车', '自定义...'
            ]
            hotkey, ok = QInputDialog.getItem(self, '选择热键', '热键类型：', hotkeys, 0, False)
            if not ok: return
            key_map = {
                'Ctrl+C 复制': ['ctrl', 'c'],
                'Ctrl+V 粘贴': ['ctrl', 'v'],
                'Ctrl+X 剪切': ['ctrl', 'x'],
                'Ctrl+Z 撤销': ['ctrl', 'z'],
                'Ctrl+Y 重做': ['ctrl', 'y'],
                'Ctrl+A 全选': ['ctrl', 'a'],
                'Alt+Tab 切换窗口': ['alt', 'tab'],
                'Win+D 显示桌面': ['win', 'd'],
                'F5 刷新': ['f5'],
                'Delete 删除': ['delete'],
                'Insert 插入': ['insert'],
                'Home 首位': ['home'],
                'End 末位': ['end'],
                'PageUp 上翻页': ['pageup'],
                'PageDown 下翻页': ['pagedown'],
                'Enter 回车': ['enter']
            }
            if hotkey == '自定义...':
                keys, ok = QInputDialog.getText(self, '自定义热键', '请输入热键组合(如 ctrl+shift+s):')
                if not ok or not keys.strip():
                    return
                key_seq = [k.strip() for k in keys.lower().split('+') if k.strip()]
                desc = f'热键: {"+".join(key_seq).upper()}'
            else:
                key_seq = key_map.get(hotkey, [])
                desc = f'热键: {hotkey}'
            step = {'type': '热键', 'key_seq': key_seq}
        else:
            return
        self.workflow.append(step)
        self.workflow_list.addItem(desc)
        self.log_msg(f'添加步骤: {desc}')

    def del_step(self):
        """删除选中的工作流步骤"""
        row = self.workflow_list.currentRow()
        if row >= 0:
            self.workflow_list.takeItem(row)
            step = self.workflow.pop(row)
            self.log_msg(f'删除步骤: {step}')

    def run_workflow(self):
        """执行工作流中的所有步骤"""
        if not self.workflow:
            QMessageBox.information(self, '提示', '请先添加操作步骤！')
            return
        self.label.setText('即将执行自定义工作流，请切换到目标窗口...')
        QApplication.processEvents()
        time.sleep(2)
        for idx, step in enumerate(self.workflow):
            try:
                t = step.get('type', '')
                if t == '移动':
                    pyautogui.moveTo(step['x'], step['y'], duration=1)
                    self.log_msg(f'[{idx+1}] 鼠标移动到({step["x"]},{step["y"]})')
                elif t == '单击':
                    pyautogui.moveTo(step['x'], step['y'], duration=1)
                    pyautogui.click()
                    self.log_msg(f'[{idx+1}] 鼠标单击({step["x"]},{step["y"]})')
                elif t == '双击':
                    pyautogui.moveTo(step['x'], step['y'], duration=1)
                    pyautogui.doubleClick()
                    self.log_msg(f'[{idx+1}] 鼠标双击({step["x"]},{step["y"]})')
                elif t == '右击':
                    pyautogui.moveTo(step['x'], step['y'], duration=1)
                    pyautogui.rightClick()
                    self.log_msg(f'[{idx+1}] 鼠标右击({step["x"]},{step["y"]})')
                elif t == '拖动':
                    pyautogui.moveTo(step['x'], step['y'], duration=1)
                    pyautogui.dragRel(step.get('dx', 100), 0, duration=1)
                    self.log_msg(f'[{idx+1}] 鼠标从({step["x"]},{step["y"]})水平拖动{step.get("dx", 100)}像素')
                elif t == '键盘输入':
                    text = step.get('text', '')
                    if text:
                        pyperclip.copy(text)
                        pyautogui.hotkey('ctrl', 'v')
                        pyautogui.press('enter')
                        self.log_msg(f'[{idx+1}] 键盘输入: {text}')
                elif t == '延迟':
                    sec = step.get('sec', 1)
                    self.log_msg(f'[{idx+1}] 延迟{sec}秒')
                    time.sleep(sec)
                elif t == '热键':
                    key_seq = step.get('key_seq', [])
                    if key_seq:
                        pyautogui.hotkey(*key_seq)
                        self.log_msg(f'[{idx+1}] 执行热键: {("+".join(key_seq)).upper()}')
                else:
                    self.log_msg(f'[{idx+1}] 跳过无法识别的步骤: {step}')
                QApplication.processEvents()
            except Exception as e:
                self.log_msg(f'[{idx+1}] 步骤发生错误: {e}')
        self.label.setText('自定义工作流执行完毕！')
        self.log_msg('自定义工作流执行完毕！')

    def toggle_recording(self):
        """切换录制状态"""
        if not self.recording:
            self.record_btn.setText('停止录制并保存')
            self.recording = True
            self.recorded_events = []
            self._recording_saved = False  # 防止重复保存
            self._last_move_pos = None  # 录制开始时重置
            self._move_start_pos = None  # 录制开始时重置
            self.log_msg('开始录制用户键鼠操作...')
            self.start_recording()
        else:
            self.record_btn.setText('开始录制用户操作')
            self.recording = False
            self.stop_recording()
            if not getattr(self, '_recording_saved', False):
                self.save_recorded_events()
                self._recording_saved = True
            self.log_msg('录制已停止，操作已保存。')
            # 防止抖动，录制结束后短暂禁用按钮
            self.record_btn.setEnabled(False)
            QTimer.singleShot(500, lambda: self.record_btn.setEnabled(True))

    def start_recording(self):
        """开始录制用户操作"""
        # 启动鼠标和键盘监听线程
        self.mouse_listener = mouse.Listener(
            on_move=self.on_mouse_move,
            on_click=self.on_mouse_click,
            on_scroll=self.on_mouse_scroll)
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release)
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def stop_recording(self):
        """停止录制用户操作"""
        # 健壮性增强，防止监听器未启动或已关闭时报错
        try:
            if hasattr(self, 'mouse_listener') and self.mouse_listener is not None:
                self.mouse_listener.stop()
        except Exception as e:
            self.log_signal.emit(f'停止鼠标监听器异常: {e}')
        try:
            if hasattr(self, 'keyboard_listener') and self.keyboard_listener is not None:
                self.keyboard_listener.stop()
        except Exception as e:
            self.log_signal.emit(f'停止键盘监听器异常: {e}')
        self.mouse_listener = None
        self.keyboard_listener = None
        # 彻底释放监听器引用，防止线程残留
        gc.collect()

    def on_mouse_move(self, x, y):
        """录制鼠标移动事件"""
        if self.recording:
            # 合并连续移动，减少日志和内存压力
            if self.recorded_events and self.recorded_events[-1]['type'] == 'move':
                self.recorded_events[-1].update({'x': x, 'y': y, 'time': time.time()})
            else:
                self.recorded_events.append({'type': 'move', 'x': x, 'y': y, 'time': time.time()})
            if self._move_start_pos is None:
                self._move_start_pos = (x, y)
            x1, y1 = self._move_start_pos
            move_msg = f"鼠标移动: from ({x1}, {y1}) to ({x}, {y})"
            
            # 更新日志区，优化过滤：不使用lastBlock直接操作
            self.log.moveCursor(self.log.textCursor().End)
            cursor = self.log.textCursor()
            cursor.select(cursor.LineUnderCursor)
            text_line = cursor.selectedText()
            if text_line.startswith("鼠标移动: from "):
                cursor.removeSelectedText()
                cursor.insertText(move_msg)
            else:
                self.log.append(move_msg)
            
            self._last_move_pos = (x, y)

    def on_mouse_click(self, x, y, button, pressed):
        """录制鼠标点击事件"""
        if self.recording and pressed:
            now = time.time()
            # 检查上一条是否为同一位置的单击，且时间间隔<1秒才算双击
            if self.recorded_events and self.recorded_events[-1]['type'] == 'click':
                prev = self.recorded_events[-1]
                interval = now - prev['time']
                if prev['x'] == x and prev['y'] == y and prev['button'] == str(button) and interval < 1.0:
                    # 替换为双击
                    self.recorded_events[-1] = {'type': 'double_click', 'x': x, 'y': y, 'button': str(button), 'time': now}
                    # 替换日志区上一条单击为双击 - 优化实现
                    self.log_signal.emit(f'识别双击({x},{y})，更新日志和记录')
                    self._last_move_pos = None
                    self._move_start_pos = None
                    return
            # 否则正常追加单击
            self.recorded_events.append({'type': 'click', 'x': x, 'y': y, 'button': str(button), 'pressed': pressed, 'time': now})
            self.log.append(f"单击({x},{y})")
            self._last_move_pos = None
            self._move_start_pos = None

    def on_mouse_scroll(self, x, y, dx, dy):
        """录制鼠标滚动事件"""
        if self.recording:
            self.recorded_events.append({'type': 'scroll', 'x': x, 'y': y, 'dx': dx, 'dy': dy, 'time': time.time()})
            self.log.append(f"滚动({x},{y}) dx={dx},dy={dy}")
            self._last_move_pos = None
            self._move_start_pos = None

    def on_key_press(self, key):
        """录制键盘按下事件"""
        if self.recording:
            try:
                k = key.char if hasattr(key, 'char') else str(key)
            except Exception:
                k = str(key) if key is not None else ''
                
            self.recorded_events.append({'type': 'key_press', 'key': k, 'time': time.time()})
            # 日志显示常见按键
            desc = self._event_to_desc({'type': 'key_press', 'key': k})
            self.log.append(desc)
            self._last_move_pos = None
            self._move_start_pos = None

    def on_key_release(self, key):
        """录制键盘释放事件"""
        if self.recording:
            try:
                k = key.char if hasattr(key, 'char') else str(key) 
            except Exception:
                k = str(key) if key is not None else ''
                
            self.recorded_events.append({'type': 'key_release', 'key': k, 'time': time.time()})
            desc = self._event_to_desc({'type': 'key_release', 'key': k})
            self.log.append(desc)
            self._last_move_pos = None
            self._move_start_pos = None

    def _event_to_desc(self, e):
        """将事件转换为描述文本"""
        t = e.get('type', '')
        if t == 'move':
            x, y = e.get('x', ''), e.get('y', '')
            return f"鼠标移动: to ({x}, {y})"
        elif t == 'click':
            return f"单击({e.get('x','')},{e.get('y','')})"
        elif t == 'double_click':
            return f"双击({e.get('x','')},{e.get('y','')})"
        elif t == 'right_click':
            return f"右击({e.get('x','')},{e.get('y','')})"
        elif t == 'drag':
            return f"拖拽({e.get('x1','')},{e.get('y1','')})→({e.get('x2','')},{e.get('y2','')})"
        elif t == 'scroll':
            return f"滚动({e.get('x','')},{e.get('y','')}) dx={e.get('dx','')},dy={e.get('dy','')}"
        elif t == 'key_press':
            k = e.get('key','')
            key_map = {
                'Key.backspace': 'Backspace', 'Key.enter': 'Enter', 'Key.space': 'Space', 'Key.tab': 'Tab',
                'Key.esc': 'Esc', 'Key.delete': 'Delete', 'Key.shift': 'Shift', 'Key.ctrl_l': 'Ctrl', 'Key.ctrl_r': 'Ctrl',
                'Key.alt_l': 'Alt', 'Key.alt_r': 'Alt', 'Key.caps_lock': 'CapsLock', 'Key.insert': 'Insert',
            }
            if k in key_map:
                return f"按键: {key_map[k]}"
            if str(k).startswith('Key.'):
                return f"按键: {str(k)[4:].capitalize()}"
            return f"按键: {k}"
        elif t == 'key_release':
            k = e.get('key','')
            key_map = {
                'Key.backspace': 'Backspace', 'Key.enter': 'Enter', 'Key.space': 'Space', 'Key.tab': 'Tab',
                'Key.esc': 'Esc', 'Key.delete': 'Delete', 'Key.shift': 'Shift', 'Key.ctrl_l': 'Ctrl', 'Key.ctrl_r': 'Ctrl',
                'Key.alt_l': 'Alt', 'Key.alt_r': 'Alt', 'Key.caps_lock': 'CapsLock', 'Key.insert': 'Insert',
            }
            if k in key_map:
                return f"松键: {key_map[k]}"
            if str(k).startswith('Key.'):
                return f"松键: {str(k)[4:].capitalize()}"
            return f"松键: {k}"
        elif t == 'text':
            return f"键盘输入: {e.get('text','')}"
        elif t == 'hotkey':
            return f"热键: {'+'.join(e.get('key_seq', []))}"
        else:
            return str(e)

    def replay_history_file(self, jsonfile):
        """回放历史记录文件"""
        try:
            with open(jsonfile, 'r', encoding='utf-8') as f:
                events = json.load(f)
        except Exception as e:
            self.log_signal.emit(f'读取{jsonfile}失败: {e}')
            return
            
        self.replaying = True  # 设置回放状态
        self.log_signal.emit(f'开始回放 {jsonfile} ...')
        
        for idx, e in enumerate(events):            # 检查是否被用户中断
            if not self.replaying:
                self.log_signal.emit('回放被用户中断')
                break
                
            try:
                t = e.get('type', '')
                if t == 'move':
                    x, y = e.get('x'), e.get('y')
                    if x is not None and y is not None:
                        pyautogui.moveTo(x, y, duration=0.2)
                        self.log_signal.emit(f'[{idx+1}] 鼠标移动到({x},{y})')
                elif t == 'click':
                    x, y = e.get('x'), e.get('y')
                    if x is not None and y is not None:
                        pyautogui.moveTo(x, y, duration=0.1)
                        pyautogui.click()
                        self.log_signal.emit(f'[{idx+1}] 鼠标单击({x},{y})')
                elif t == 'double_click':
                    x, y = e.get('x'), e.get('y')
                    if x is not None and y is not None:
                        pyautogui.moveTo(x, y, duration=0.1)
                        pyautogui.doubleClick()
                        self.log_signal.emit(f'[{idx+1}] 鼠标双击({x},{y})')
                elif t == 'right_click':
                    x, y = e.get('x'), e.get('y')
                    if x is not None and y is not None:
                        pyautogui.moveTo(x, y, duration=0.1)
                        pyautogui.rightClick()
                        self.log_signal.emit(f'[{idx+1}] 鼠标右击({x},{y})')
                elif t == 'scroll':
                    x, y = e.get('x'), e.get('y')
                    dy = e.get('dy', 0)
                    if x is not None and y is not None:
                        pyautogui.moveTo(x, y, duration=0.1)
                        pyautogui.scroll(dy)
                        self.log_signal.emit(f'[{idx+1}] 鼠标滚动({x},{y}) dy={dy}')
                elif t == 'key_press':
                    k = e.get('key', '')
                    if k and len(k) == 1:
                        pyautogui.press(k)
                        self.log_signal.emit(f'[{idx+1}] 按键: {k}')
                    elif k and str(k).startswith('Key.'):
                        key_map = {
                            'Key.enter': 'enter', 'Key.space': 'space', 'Key.tab': 'tab',
                            'Key.backspace': 'backspace', 'Key.delete': 'delete', 'Key.esc': 'esc',
                            'Key.shift': 'shift', 'Key.ctrl_l': 'ctrl', 'Key.ctrl_r': 'ctrl',
                            'Key.alt_l': 'alt', 'Key.alt_r': 'alt', 'Key.caps_lock': 'capslock',
                            'Key.insert': 'insert', 'Key.home': 'home', 'Key.end': 'end',
                            'Key.page_up': 'pageup', 'Key.page_down': 'pagedown',
                        }
                        keyname = key_map.get(k, k[4:].lower())
                        if keyname:  # 添加非空检查
                            pyautogui.press(keyname)
                            self.log_signal.emit(f'[{idx+1}] 按键: {keyname}')
                elif t == 'key_release':
                    pass  # 忽略松键
                time.sleep(0.05)
            except Exception as e:
                self.log_signal.emit(f'[{idx+1}] 回放出错: {e}')
        
        self.replaying = False  # 重置回放状态
        self.log_signal.emit(f'{jsonfile} 回放完毕！')

    def replay_recorded_events(self):
        """回放录制的事件"""
        # 优先回放当前选中的历史json，否则回放user_actions.json
        jsonfile = getattr(self, 'current_history_json', None)
        if not jsonfile:
            jsonfile = 'user_actions.json'
          # 创建并启动回放线程
        self.replay_thread = threading.Thread(target=lambda: self.replay_history_file(jsonfile))
        self.replay_thread.setDaemon(True)
        self.replay_thread.start()
        
    def on_history_item_clicked(self, item):
        """处理点击历史记录列表项事件"""
        # 预览txt日志到自定义工作流区，并自动推断并记录对应json文件
        fname = item.text()
        if fname.endswith('.txt'):
            jsonfile = fname.replace('.txt', '.json')
            if os.path.exists(jsonfile):
                try:
                    self.current_history_json = jsonfile
                    self.log_msg(f'已选择历史记录: {fname}')
                    
                    # 读取JSON文件并转换为工作流
                    with open(jsonfile, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                    
                    # 清空当前工作流
                    self.workflow = []
                    self.workflow_list.clear()
                    
                    # 将历史记录转换为工作流步骤
                    for event in events:
                        workflow_step = self._convert_event_to_workflow_step(event)
                        if workflow_step:
                            self.workflow.append(workflow_step)
                            desc = self._get_workflow_step_desc(workflow_step)
                            self.workflow_list.addItem(desc)
                    
                    self.log_msg(f'已将历史记录转换为工作流，共{len(self.workflow)}个步骤')
                    
                    # 同时显示预览内容
                    with open(fname, 'r', encoding='utf-8') as f:
                        preview = f.read()
                        self.log_msg(f'历史记录预览:\n{preview[:200]}...' if len(preview) > 200 else f'历史记录预览:\n{preview}')
                        
                except Exception as e:
                    self.log_msg(f'读取历史记录失败: {e}')
            else:
                self.log_msg(f'对应的JSON文件不存在: {jsonfile}')

    def save_recorded_events(self):
        """保存录制的事件为历史记录"""
        # 保存主文件
        with open('user_actions.json', 'w', encoding='utf-8') as f:
            json.dump(self.recorded_events, f, ensure_ascii=False, indent=2)
        
        # 保存历史副本
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = f'user_actions_{ts}.json'
        with open(backup, 'w', encoding='utf-8') as f:
            json.dump(self.recorded_events, f, ensure_ascii=False, indent=2)
        
        # 保存操作描述为txt
        txtfile = f'user_actions_{ts}.txt'
        with open(txtfile, 'w', encoding='utf-8') as f:
            for e in self.recorded_events:
                desc = self._event_to_desc(e)
                f.write(desc + '\n')
        
        self.log_msg(f'操作已保存到 user_actions.json、{backup} 和 {txtfile}')
        self.refresh_history_list()
        
    def save_workflow_as_history(self):
        """保存当前工作流为新的历史记录"""
        if not self.workflow:
            QMessageBox.information(self, '提示', '当前工作流为空，无法保存！')
            return
        
        # 请求自定义名称
        name, ok = QInputDialog.getText(self, '保存工作流', '请输入工作流名称:', text='自定义工作流')
        if not ok or not name.strip():
            return
        
        safe_name = name.strip().replace(' ', '_').replace('/', '_').replace('\\', '_')
        
        try:            # 转换工作流为事件格式（使用英文字段以兼容回放）
            events = []
            for step in self.workflow:
                event = self._convert_workflow_step_to_event(step)
                if event:
                    event['time'] = str(time.time())  # 转换为字符串
                    events.append(event)
            
            # 保存JSON和TXT文件
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            json_filename = f'user_actions_{safe_name}_{ts}.json'
            txt_filename = f'user_actions_{safe_name}_{ts}.txt'
            
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            
            with open(txt_filename, 'w', encoding='utf-8') as f:
                for step in self.workflow:
                    desc = self._get_workflow_step_desc(step)
                    f.write(desc + '\n')
            
            self.log_msg(f'工作流已保存: {json_filename}')
            self.refresh_history_list()
            QMessageBox.information(self, '成功', f'工作流已保存为历史记录:\n{txt_filename}')
        except Exception as e:
            self.log_msg(f'保存失败: {e}')
            QMessageBox.critical(self, '错误', f'保存失败: {e}')

    def _get_workflow_step_desc(self, step):
        """获取工作流步骤的描述"""
        t = step.get('type', '')
        if t in ['移动', '单击', '双击', '右击']:
            return f'{t}到({step.get("x", 0)},{step.get("y", 0)})'
        elif t == '拖动':
            return f'{t}到({step.get("x", 0)},{step.get("y", 0)})，水平拖动{step.get("dx", 0)}px'
        elif t == '键盘输入':
            return f'键盘输入: {step.get("text", "")}'
        elif t == '延迟':
            return f'延迟{step.get("sec", 1)}秒'
        elif t == '热键':
            keys_str = "+".join(step.get("key_seq", []))
            return f'热键: {keys_str.upper()}'
        else:
            return str(step)

    def rename_history_record(self):
        """重命名选中的历史记录"""
        current_item = self.history_list.currentItem()
        if not current_item:
            QMessageBox.information(self, '提示', '请先选择要重命名的历史记录！')
            return
        
        old_txt_file = current_item.text()
        if not old_txt_file.endswith('.txt'):
            return
        
        # 解析原文件名获取基本信息
        match = None
        import re
        match = re.match(r'user_actions_(.+)_(\d{8}_\d{6})\.txt', old_txt_file)
        if match:
            old_name = match.group(1)
            timestamp = match.group(2)
        else:
            old_name = old_txt_file.replace('user_actions_', '').replace('.txt', '')
            timestamp = ''
        
        # 询问新名称
        new_name, ok = QInputDialog.getText(self, '重命名历史记录', '请输入新名称:', text=old_name)
        if not ok or not new_name.strip():
            return
        
        safe_new_name = new_name.strip().replace(' ', '_').replace('/', '_').replace('\\', '_')
        
        # 生成新文件名
        if timestamp:
            new_txt_file = f'user_actions_{safe_new_name}_{timestamp}.txt'
            new_json_file = f'user_actions_{safe_new_name}_{timestamp}.json'
            old_json_file = old_txt_file.replace('.txt', '.json')
        else:
            new_txt_file = f'user_actions_{safe_new_name}.txt'
            new_json_file = f'user_actions_{safe_new_name}.json'
            old_json_file = old_txt_file.replace('.txt', '.json')
        
        try:
            # 重命名文件
            if os.path.exists(old_txt_file):
                os.rename(old_txt_file, new_txt_file)
            if os.path.exists(old_json_file):
                os.rename(old_json_file, new_json_file)
            
            self.log_msg(f'历史记录已重命名: {old_txt_file} -> {new_txt_file}')
            self.refresh_history_list()
            QMessageBox.information(self, '成功', f'历史记录已重命名为: {new_txt_file}')
        except Exception as e:
            self.log_msg(f'重命名失败: {e}')
            QMessageBox.critical(self, '错误', f'重命名失败: {e}')

    def delete_history_record(self):
        """删除选中的历史记录"""
        current_item = self.history_list.currentItem()
        if not current_item:
            QMessageBox.information(self, '提示', '请先选择要删除的历史记录！')
            return
        
        txt_file = current_item.text()
        if not txt_file.endswith('.txt'):
            return
        
        # 确认删除
        reply = QMessageBox.question(self, '确认删除', f'确定要删除历史记录 "{txt_file}" 吗？', 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        
        try:
            # 删除txt和json文件
            json_file = txt_file.replace('.txt', '.json')
            if os.path.exists(txt_file):
                os.remove(txt_file)
            if os.path.exists(json_file):
                os.remove(json_file)
            
            self.log_msg(f'已删除历史记录: {txt_file}')
            self.refresh_history_list()
            QMessageBox.information(self, '成功', f'历史记录 "{txt_file}" 已删除')
        except Exception as e:
            self.log_msg(f'删除失败: {e}')
            QMessageBox.critical(self, '错误', f'删除失败: {e}')

    def refresh_history_list(self):
        """刷新历史记录列表"""
        self.history_list.clear()
        for fname in sorted(glob.glob('user_actions_*.txt'), reverse=True):
            self.history_list.addItem(fname)

    def _convert_event_to_workflow_step(self, event):
        """将历史记录事件转换为工作流步骤"""
        event_type = event.get('type', '')
        
        # 基础的鼠标操作
        if event_type == 'move':
            return {'type': '移动', 'x': event.get('x', 0), 'y': event.get('y', 0)}
        elif event_type == 'click':
            return {'type': '单击', 'x': event.get('x', 0), 'y': event.get('y', 0)}
        elif event_type == 'double_click':
            return {'type': '双击', 'x': event.get('x', 0), 'y': event.get('y', 0)}
        elif event_type == 'right_click':
            return {'type': '右击', 'x': event.get('x', 0), 'y': event.get('y', 0)}
        elif event_type == 'scroll':
            # 鼠标滚动事件暂时跳过，因为工作流中没有对应的操作
            return None
        
        # 键盘操作 - 简化处理
        elif event_type == 'key_press':
            key = event.get('key', '')
            if key and len(key) == 1 and key.isalnum():
                # 对于单个字符，转换为键盘输入
                return {'type': '键盘输入', 'text': key}
            elif str(key).startswith('Key.'):
                # 对于特殊按键，转换为热键
                key_name = str(key)[4:].lower()
                if key_name in ['enter', 'space', 'tab', 'backspace', 'delete', 'esc']:
                    return {'type': '热键', 'key_seq': [key_name]}
            return None
        
        # 已经是工作流格式的步骤（从保存的工作流历史记录中读取）
        elif event_type in ['移动', '单击', '双击', '右击', '拖动', '键盘输入', '延迟', '热键']:
            return event
        
        # 其他类型暂时跳过
        return None

    def _convert_workflow_step_to_event(self, step):
        """将工作流步骤转换为历史记录事件格式（英文字段）"""
        step_type = step.get('type', '')
        
        # 鼠标操作转换
        if step_type == '移动':
            return {'type': 'move', 'x': step.get('x', 0), 'y': step.get('y', 0)}
        elif step_type == '单击':
            return {'type': 'click', 'x': step.get('x', 0), 'y': step.get('y', 0)}
        elif step_type == '双击':
            return {'type': 'double_click', 'x': step.get('x', 0), 'y': step.get('y', 0)}
        elif step_type == '右击':
            return {'type': 'right_click', 'x': step.get('x', 0), 'y': step.get('y', 0)}
        elif step_type == '拖动':
            # 拖动操作转换为移动 + 按住 + 移动 + 释放的序列，这里简化为移动
            return {'type': 'move', 'x': step.get('x', 0), 'y': step.get('y', 0)}
        
        # 键盘操作转换
        elif step_type == '键盘输入':
            text = step.get('text', '')
            # 为了简化，将文本输入转换为一系列字符按键事件
            if text:
                # 返回第一个字符的按键事件，实际应用中可能需要更复杂的处理
                return {'type': 'key_press', 'key': text[0] if len(text) > 0 else ''}
        elif step_type == '热键':
            key_seq = step.get('key_seq', [])
            if key_seq:
                # 转换为按键事件，使用第一个键
                key_name = key_seq[0] if key_seq else ''
                return {'type': 'key_press', 'key': f'Key.{key_name}'}
        
        # 延迟操作无法直接转换为事件，跳过
        elif step_type == '延迟':
            return None
        
        # 未知类型，尝试原样返回
        return step

if __name__ == '__main__':
    try:
        print("程序启动，正在创建窗口...")
        print("创建 QApplication...")
        app = QApplication(sys.argv)
        print("QApplication 创建成功")
        
        print("创建 AutoMouseKeyboard 窗口...")
        window = AutoMouseKeyboard()
        print("窗口对象创建成功")
        
        print("显示窗口...")
        window.show()
        print("窗口已显示，程序运行中...")
        
        # 进入事件循环
        sys.exit(app.exec_())
    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")
