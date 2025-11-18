from module.automation.input_base import InputBase
from module.cloud import CloudGameManager
import time

class BrowserInput(InputBase):
    SPECIAL_KEY_MAP = {
        "esc":      {"key": "Escape",      "code": "Escape",      "vk": 27},
        "enter":    {"key": "Enter",       "code": "Enter",       "vk": 13},
        "space":    {"key": " ",           "code": "Space",       "vk": 32},
        "tab":      {"key": "Tab",         "code": "Tab",         "vk": 9},
        "backspace":{"key": "Backspace",   "code": "Backspace",   "vk": 8},
        "delete":   {"key": "Delete",      "code": "Delete",      "vk": 46},
        "arrowup":    {"key": "ArrowUp",    "code": "ArrowUp",    "vk": 38},
        "arrowdown":  {"key": "ArrowDown",  "code": "ArrowDown",  "vk": 40},
        "arrowleft":  {"key": "ArrowLeft",  "code": "ArrowLeft",  "vk": 37},
        "arrowright": {"key": "ArrowRight", "code": "ArrowRight", "vk": 39},
    }
    
    for i in range(1, 13):
        SPECIAL_KEY_MAP[f"f{i}"] = {
            "key": f"F{i}",
            "code": f"F{i}",
            "vk": 111 + i
        }

    CHAR_KEY_MAP = {
        # a-z
        **{chr(i): {
            "key": chr(i).upper(),
            "code": f"Key{chr(i).upper()}",
            "vk": ord(chr(i).upper())
        } for i in range(97, 123)},
        # 0-9
        **{str(i): {
            "key": str(i),
            "code": f"Digit{str(i)}",
            "vk": 48 + i
        } for i in range(0, 10)},
    }

    def __init__(self, cloud_game: CloudGameManager, logger):
        self.cloud_game = cloud_game
        self.logger = logger
        self.last_x = 0
        self.last_y = 0

    # ---------------- Mouse ----------------
    def mouse_move(self, x, y):
        """
        TODO 这个函数目前有问题，无法实现视角旋转
        """
        self.logger.warning("浏览器无法通过鼠标移动来转视角")
        self.last_x, self.last_y = x, y
        try:
            self.cloud_game.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": x, "y": y,
                "pointerType": "mouse"
            })
            self.logger.debug(f"鼠标移动 ({x}, {y})")
        except Exception as e:
            self.logger.error(f"鼠标移动出错：{e}")

    def mouse_down(self, x, y):
        self.last_x, self.last_y = x, y
        try:
            self.cloud_game.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "button": "left",
                "buttons": 1,
                "x": x, "y": y,
                "clickCount": 1,
                "pointerType": "mouse"
            })
            self.logger.debug(f"鼠标按下 ({x}, {y})")
        except Exception as e:
            self.logger.error(f"鼠标按下出错：{e}")

    def mouse_up(self):
        try:
            self.cloud_game.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "button": "left",
                "buttons": 1,
                "x": self.last_x, "y": self.last_y,
                "clickCount": 1,
                "pointerType": "mouse"
            })
            self.logger.debug(f"鼠标释放 ({self.last_x}, {self.last_y})")
        except Exception as e:
            self.logger.error(f"鼠标释放出错：{e}")

    def mouse_click(self, x, y):
        self.mouse_down(x, y)
        self.mouse_up()
        self.logger.debug(f"鼠标点击 ({x}, {y})")

    def mouse_scroll(self, count, direction=-1, pause=True):
        """
        count 次数，一次大概 10 像素
        direction -1 为向下滚，1 为向上滚
        """
        deltaY = -10 * direction / abs(direction)
        try:
            for i in range(count):
                self.cloud_game.execute_cdp_cmd("Input.dispatchMouseEvent", {
                    "type": "mouseWheel",
                    "x": self.last_x, "y": self.last_y,
                    "deltaX": 0,
                    "deltaY": deltaY,
                    "pointerType": "mouse"
                })
            self.logger.debug(f"滚轮滚动 count={count}")
        except Exception as e:
            self.logger.error(f"鼠标滚轮出错：{e}")

    # ---------------- Keyboard ----------------
    def press_key(self, key, wait_time=0.2):
        k = key.lower()
        if k in self.SPECIAL_KEY_MAP:
            info = self.SPECIAL_KEY_MAP[k]
        elif k in self.CHAR_KEY_MAP:
            info = self.CHAR_KEY_MAP[k]
        else:
            self.logger.error(f"未知按键（云游戏不支持 text 模式）：{key}")
            return

        payload = {
            "key": info["key"],
            "code": info["code"],
            "windowsVirtualKeyCode": info["vk"],
            "nativeVirtualKeyCode": info["vk"],
            "modifiers": 0,
            "text": ""
        }

        try:
            self.cloud_game.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", **payload})
            time.sleep(wait_time)
            self.cloud_game.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", **payload})
            self.logger.debug(f"云游戏按键：{key}")
        except Exception as e:
            self.logger.error(f"按键 {key} 出错：{e}")

    def secretly_press_key(self, key, wait_time=0.2):
        # 改为有效云游戏按键发送
        self.press_key(key, wait_time)
        self.logger.debug("键盘按下 *")

    def press_mouse(self, wait_time=0.2):
        try:
            self.cloud_game.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "button": "left",
                "buttons": 1,
                "x": self.last_x, "y": self.last_y,
                "clickCount": 1,
                "pointerType": "mouse"
            })
            time.sleep(wait_time)
            self.cloud_game.execute_cdp_cmd("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "button": "left",
                "buttons": 1,
                "x": self.last_x, "y": self.last_y,
                "clickCount": 1,
                "pointerType": "mouse"
            })
            self.logger.debug(f"按下鼠标左键 ({self.last_x}, {self.last_y})")
        except Exception as e:
            self.logger.error(f"按下鼠标左键出错：{e}")

    def secretly_write(self, text, interval=0.1):
        try:
            for ch in text:
                if ch.lower() in self.CHAR_KEY_MAP:
                    info = self.CHAR_KEY_MAP[ch.lower()]
                    payload = {
                        "key": info["key"],
                        "code": info["code"],
                        "windowsVirtualKeyCode": info["vk"],
                        "nativeVirtualKeyCode": info["vk"],
                        "modifiers": 0,
                        "text": ""
                    }
                    self.cloud_game.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyDown", **payload})
                    self.cloud_game.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", **payload})
                else:
                    self.logger.warning(f"secretly_write 不支持的字符: {ch}")
                time.sleep(interval)
            self.logger.debug("键盘输入 ***")
        except Exception as e:
            self.logger.error(f"键盘输入 *** 出错：{e}")
