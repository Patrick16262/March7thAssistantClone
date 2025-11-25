import time
from module.automation.input_base import InputBase

class BrowserInput(InputBase):
    SPECIAL_KEY_MAP = {
        "esc": "Escape",
        "enter": "Enter",
        "space": " ",
        "tab": "Tab",
        "backspace": "Backspace",
        "delete": "Delete",
        "arrowup": "ArrowUp",
        "arrowdown": "ArrowDown",
        "arrowleft": "ArrowLeft",
        "arrowright": "ArrowRight",
    }
    for i in range(1, 13):
        SPECIAL_KEY_MAP[f"f{i}"] = f"F{i}"

    def __init__(self, cloud_game, logger):
        """
        cloud_game: CloudGameController
        """
        self.cloud_game = cloud_game
        self.run_action = self.cloud_game.run_in_playwright_thread
        self.logger = logger
        self.last_x = 0
        self.last_y = 0

    def focus(self):
        """确保鼠标在游戏区域内"""
        try:
            if self.cloud_game.page:
                self.run_action(self.cloud_game.page.mouse.move, self.last_x, self.last_y)
        except Exception as e:
            self.logger.error(f"获取焦点出错：{e}")

    # ---------------- Mouse ----------------
    def mouse_click(self, x=None, y=None):
        '''在屏幕上的（x，y）位置执行鼠标点击操作'''
        if x is not None and y is not None:
            self.mouse_move(x, y)
        self.mouse_down()
        self.mouse_up()
        self.logger.debug(f"鼠标点击 ({self.last_x}, {self.last_y})")

    def mouse_down(self, x=None, y=None):
        '''在屏幕上的（x，y）位置按下鼠标按钮'''
        if x is not None and y is not None:
            self.last_x, self.last_y = x, y
        try:
            self.run_action(self.cloud_game.page.mouse.down)
            self.logger.debug(f"鼠标按下 ({self.last_x}, {self.last_y})")
        except Exception as e:
            self.logger.error(f"鼠标按下出错：{e}")

    def mouse_up(self):
        '''释放鼠标按钮'''
        try:
            self.run_action(self.cloud_game.page.mouse.up)
            self.logger.debug(f"鼠标释放 ({self.last_x}, {self.last_y})")
        except Exception as e:
            self.logger.error(f"鼠标释放出错：{e}")
        
    def mouse_move(self, x, y):
        '''将鼠标光标移动到屏幕上的（x，y）位置'''
        self.last_x, self.last_y = x, y
        try:
            self.run_action(self.cloud_game.page.mouse.move, x, y)
            self.logger.debug(f"鼠标移动 ({x}, {y})")
        except Exception as e:
            self.logger.error(f"鼠标移动出错：{e}")

    def mouse_scroll(self, count, direction=-1, pause=True):
        '''滚动鼠标滚轮，方向和次数由参数指定'''
        delta = -8 * direction
        try:
            for _ in range(count):
                self.run_action(self.cloud_game.page.mouse.wheel, 0, delta)
            self.logger.debug(f"滚轮滚动 count={count} direction={direction}")
        except Exception as e:
            self.logger.error(f"鼠标滚轮出错：{e}")

    # ---------------- Keyboard ----------------
    def press_key(self, key, wait_time=0.2):
        '''模拟键盘按键，可以指定按下的时间'''
        self.focus()
        try:
            if key in self.SPECIAL_KEY_MAP:
                self.run_action(self.cloud_game.page.keyboard.press, self.SPECIAL_KEY_MAP[key], delay=int(wait_time*1000))
            else:
                self.run_action(self.cloud_game.page.keyboard.press, key, delay=int(wait_time*1000))
            self.logger.debug(f"按键按下：{key}")
            return
        except Exception as e:
            self.logger.error(f"按键 {key} 出错：{e}")

    def secretly_press_key(self, key, wait_time=0.2):
        '''(不输出具体键位)模拟键盘按键，可以指定按下的时间'''
        self.run_action(self.cloud_game.page.keyboard.press, key, delay=int(wait_time*1000))
        self.logger.debug("键盘按下 *")

    def press_mouse(self, wait_time=0.2):
        '''模拟鼠标左键的点击操作，可以指定按下的时间'''
        try:
            self.run_action(self.mouse_down)
            time.sleep(wait_time)
            self.run_action(self.mouse_up)
            self.logger.debug(f"按下鼠标左键 ({self.last_x}, {self.last_y})")
        except Exception as e:
            self.logger.error(f"按下鼠标左键出错：{e}")

    def secretly_write(self, text, interval=0.1):
        '''模拟键盘输入字符串，可以指定字符输入间隔'''
        try:
            self.focus()
            for ch in text:
                self.run_action(self.cloud_game.page.keyboard.press, ch)
                time.sleep(interval)
            self.logger.debug("键盘输入 ***")
        except Exception as e:
            self.logger.error(f"键盘输入 *** 出错：{e}")
