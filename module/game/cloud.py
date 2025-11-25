import atexit
import os
import json
import queue
import subprocess
import sys
import threading
import psutil
import win32con
import win32gui
import win32process
from PIL import Image
from io import BytesIO
from time import sleep
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from playwright.__main__ import main as playwright_main

from module.config import Config
from module.game.base import GameControllerBase
from module.logger import Logger
from utils.encryption import wdp_encrypt, wdp_decrypt


class CloudGameController(GameControllerBase):
    COOKIE_PATH = "settings/cloud/cookies.enc"
    LOCAL_STORAGE_PATH = "settings/cloud/local_storage.json"
    GAME_URL = "https://sr.mihoyo.com/cloud"
    WINDOW_TITLE = "云·星穹铁道"
    BROWSER_TAG = "--march-7th-assistant-sr-cloud-game" 
    BROWSER_DOWNLOAD_PATH = os.path.join(os.getcwd(), "3rdparty", "WebBrowser")
    BROWSER_DATA_PATH = os.path.join(BROWSER_DOWNLOAD_PATH, "UserProfile")
    MAX_RETRIES = 3  

    def __init__(self, cfg: Config, logger: Logger):
        super().__init__(script_path=cfg.script_path, logger=logger)
        self.driver = None
        self.cfg = cfg
        self.logger = logger
        self.playwright = None
        self.context = None
        self.page = None
        self.client = None
        self.browser = None
        self.hwnd = None
        self.stop_saving_ls_event = None
        self.saving_ls_thread = None
        self.playwright_th_que = queue.Queue()
        self.playwright_thread = threading.Thread(target=self._playwright_thread_main, name="BrowserAutomationThread", daemon=True)
        self.playwright_thread.start()
        # 脚本退出时关闭浏览器，防止 playwright 报错。即使不手动关闭浏览器，playwright 也会在脚本退出时强制关闭。
        atexit.register(self.stop_game)
    
    def _playwright_thread_main(self):
        while True:
            func, args, kwargs, future = self.playwright_th_que.get()
            try:
                result = func(*args, **kwargs)
                future["result"] = result
            except Exception as e:
                future["exception"] = e
            finally:
                future["event"].set()

    def _wait_game_page_loaded(self, timeout=5):
        if not self.page:
            return
        for retry in range(self.MAX_RETRIES + 1):
            if retry > 0:
                self.log_warning(f"页面加载超时，正在刷新重试... ({retry}/{self.MAX_RETRIES})")
                self.page.reload()
            try:
                self.page.wait_for_function(
                    """() => {
                        const img = document.querySelector('#app > div.home-wrapper > picture > img');
                        return img && img.complete && img.naturalWidth > 0;
                    }""",
                    timeout=timeout*1000
                )
                return
            except PlaywrightTimeoutError:
                pass
        raise Exception("页面加载失败，多次刷新无效。")

    def _prepare_browser(self, browser_type) -> None:
        subprocess.run([sys.executable, "-m", "playwright", "install", browser_type],
                    check=True,
                    env=os.environ.copy())

    def _create_browser(self, headless=False):
        browser_type = self.cfg.browser_type
        user_data_dir = os.path.join(self.BROWSER_DATA_PATH, browser_type)
        os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = self.cfg.browser_repo_mirror
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = self.BROWSER_DOWNLOAD_PATH
        
        if browser_type == "intergrated":
            browser_type = "chromium"
            self._prepare_browser(browser_type)
        self.log_info(f"正在启动 {browser_type} 浏览器")
            
        browser_args = [
                self.BROWSER_TAG, # 用于标记是由脚本启动的
                "--lang=zh-CN", # 浏览器中文
                f"--force-device-scale-factor={float(self.cfg.browser_scale_factor)}", # 缩放比，画面过大过小可以调节这个值
                "--disable-blink-features=AutomationControlled" # 去掉自动化痕迹
            ] + self.cfg.browser_launch_argument
        if headless:
            browser_args.append("--mute-audio")
        
        self.playwright = sync_playwright().start() 
        if self.cfg.browser_persistent_enable:
            # launch_persistent_context 会用到 webdriver，导致出现 “Chrome 正由自动测试软件控制。”，
            # 这个提示除 Chrome For Testing 外均无法自动化关闭，影响模拟宇宙和锄大地运行
            # 
            # self.context = self.playwright.chromium.launch_persistent_context()
            # self.page = self.context.pages[0]
            
            # 定时保存 local storage，保存游戏内配置
            self.stop_saving_ls_event = threading.Event()
            self.saving_ls_thread = threading.Thread(
                target=self._saving_local_storage_task, 
                name="SavingLocalStorageTask"
            )
            self.saving_ls_thread.start()
        
        self.browser = self.playwright.chromium.launch(
            channel=browser_type,                       # 浏览器类型
            headless=headless,                          # 无窗口模式
            args=browser_args                           # 其他参数
        )
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},   # viewport 大小
            # permissions=["keyboard-lock"]             # keyboard-lock 权限
        )
        self.page = self.context.new_page()
        self.client = self.context.new_cdp_session(self.page)
        if self.cfg.cloud_game_fullscreen_enable and not headless:
            self._full_screen()
        self.page.goto(self.GAME_URL)
        self.page.set_viewport_size({"width": 1920, "height": 1080})
        self._load_local_storage()
        if self.cfg.browser_cookies_enable:
            self._load_cookies()
        self._refresh_page()
        self.change_window_title(self.WINDOW_TITLE)

    def _restart_browser(self, headless=False):
        self._stop_game()
        self._create_browser(headless=headless)

    def _load_local_storage(self) -> bool:
        if not self.context:
            return
        try:
            ls = {}
            try:
                with open(self.LOCAL_STORAGE_PATH, "r", encoding="utf-8") as f:
                    ls = json.load(f)
            except FileNotFoundError:
                self.log_info("未找到 Local Storage 文件")
                # 加载初始 local_storage，去掉首次运行的弹窗
                with open("assets/config/initial_local_storage.json", "r", encoding="utf-8") as f:
                    ls = json.load(f)
            
            # 修改云游戏设置
            # settings = json.loads(ls["clgm_web_app_settings_hkrpg_cn"])
            # settings["videoMode"] = 1 if self.cfg.cloud_game_smooth_first_enable else 0
            # ls["clgm_web_app_settings_hkrpg_cn"] = json.dumps(settings)

            client_config = json.loads(ls["clgm_web_app_client_store_config_hkrpg_cn"])
            # client_config["speedLimitGearId"] = self.cfg.cloud_game_video_quality
            client_config["fabPosition"]["x"] = self.cfg.cloud_game_fab_pos_x # 设置小浮球坐标
            client_config["fabPosition"]["y"] = self.cfg.cloud_game_fab_pos_y
            # client_config["showGameStatBar"] = self.cfg.cloud_game_status_bar_enable
            # client_config["gameStatBarType"] = self.cfg.cloud_game_status_bar_type
            ls["clgm_web_app_client_store_config_hkrpg_cn"] = json.dumps(client_config)

            for key, value in ls.items():
                self.context.add_init_script(
                    f'window.localStorage.setItem("{key}", {json.dumps(value)});'
                )
            return True
        except Exception as e:
            self.log_error(f"加载 Local Storage 失败: {e}")
            return False
    
    def _saving_local_storage_task(self, interval=10):
        """
        将当前页面的 local storage 导出到文件。
        """
        while not self.stop_saving_ls_event.is_set():
            if self.page and not self.page.is_closed():
                try:
                    local_storage_json = self.run_in_playwright_thread(self.page.evaluate, "JSON.stringify(window.localStorage, null, 4)")
                    os.makedirs(os.path.dirname(self.LOCAL_STORAGE_PATH), exist_ok=True)
                    with open(self.LOCAL_STORAGE_PATH, 'w', encoding='utf-8') as f:
                        f.write(local_storage_json)

                    self.log_debug(f"Local Storage 已保存到 {self.LOCAL_STORAGE_PATH}")
                except Exception as e:
                    self.log_debug(f"Local Storage 保存失败 {e}")
            
            self.stop_saving_ls_event.wait(interval)
            

    def _load_cookies(self) -> bool:
        """加载 Cookies 登录信息"""
        try:
            with open(self.COOKIE_PATH, "rb") as f:
                cookies = json.loads(wdp_decrypt(f.read()).decode())
            self.context.add_cookies(cookies)
            self.log_info("Cookies（登录状态）加载成功。")
            return True
        except FileNotFoundError:
            self.log_info("cookies 文件不存在。")
            return False
        except Exception as e:
            self.log_error(f"加载 cookies 失败: {e}")
            return False
        
    def _save_cookies(self):
        """保存 Cookies 登录信息"""
        try:
            cookies = self.context.cookies()
            os.makedirs(os.path.dirname(self.COOKIE_PATH), exist_ok=True)
            with open(self.COOKIE_PATH, "wb") as f:
                f.write(wdp_encrypt(json.dumps(cookies).encode()))
            self.log_info("登录信息保存成功。")
        except Exception as e:
            self.log_error(f"保存 cookies 失败: {e}")

    def _refresh_page(self):
        self.page.reload()
        self._wait_game_page_loaded()

    def change_window_title(self, titile):
        """修改浏览器标题为 '云·星穹铁道' 适配模拟宇宙"""
        try:
            # 适配模拟宇宙
            win32gui.SetWindowText(self.get_window_handle(), titile)
        except Exception as e:
            print("win32gui.SetWindowText 抛出异常:", e)

    def _full_screen(self):
        """强制浏览器窗口全屏"""
        try:
            window_info = self.client.send("Browser.getWindowForTarget")
            window_id = window_info["windowId"]
            self.client.send("Browser.setWindowBounds", {
                "windowId": window_id,
                "bounds": {"windowState": "fullscreen"}
            })
        except Exception as e:
            self.log_warning(f"全屏失败 {e}")

    def _check_login(self, timeout=5):
        """检查是否登录"""
        logged_in_selector = "div.user-aid.wel-card__aid"
        not_logged_in_selector = "#mihoyo-login-platform-iframe"
        try:
            self.page.wait_for_selector(f"{logged_in_selector}, {not_logged_in_selector}", timeout=timeout*1000)
            if self.page.query_selector(logged_in_selector):
                return True
            if self.page.query_selector(not_logged_in_selector):
                return False
            return None
        except PlaywrightTimeoutError:
            self.log_warning("检测登录状态超时：未出现登录或未登录标志元素")
            return None

    def _click_enter_game(self, timeout=5):
        """通过 js 点击网页‘开始游戏’按钮"""
        enter_button_selector = "div.wel-card__content--start"
        try:
            btn = self.page.wait_for_selector(enter_button_selector, timeout=timeout * 1000)
            self.page.evaluate("(el) => el.click()", btn)
        except Exception as e:
            self.log_error(f"点击进入游戏按钮游戏异常: {e}")
            raise e

    def _wait_in_queue(self, timeout=600) -> bool:
        """排队等待"""
        in_queue_selector = "[class*='waiting-in-queue']"
        cloud_game_Selector = "video"
        
        try:
            self.page.wait_for_selector(f"{cloud_game_Selector}, {in_queue_selector}", timeout=10 * 1000)
            if self.page.wait_for_selector(cloud_game_Selector, timeout=100):
                self.log_info("游戏已启动，无需排队")
                return True
            elif self.page.wait_for_selector(in_queue_selector, timeout=100):
                try:
                    self.page.wait_for_selector(in_queue_selector, state="hidden", timeout=timeout*1000)
                    self.log_info("排队成功，正在进入游戏")
                except PlaywrightTimeoutError as e:
                    self.log_error("等待排队超时")
                    return False
                return True
        except Exception as e:
            self.log_error(f"等待排队异常: {e}")
            raise e

    def _try_dump_page(self, dump_dir="logs") -> None:
        """导出当前页面"""
        try:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.page.screenshot(path=os.path.join(dump_dir, f"{ts}.png"))
            html_path = os.path.join(dump_dir, f"{ts}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.page.content())
            self.log_info(f"相关页面和截图已经保存到：{dump_dir}")
        except Exception as e:
            pass
    
    def _take_screenshot(self) -> bytes:
        """浏览器内截图"""
        if (not self.cfg.browser_headless_enable and 
                win32gui.GetWindowPlacement(self.get_window_handle())[1] == win32con.SW_SHOWMINIMIZED):
            self.log_warning("浏览器无法在最小化时截图，正在将窗口从最小化中恢复")
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        return self.page.screenshot()
        
    def _stop_game(self) -> bool:
        """停止游戏，关闭浏览器"""
        try:
            if self.stop_saving_ls_event:
                self.stop_saving_ls_event.set()
            if self.saving_ls_thread and self.saving_ls_thread.is_alive():
                self.saving_ls_thread.join()
            if self.playwright:
                self.playwright.stop()
                self.log_info("浏览器关闭成功")
            self.hwnd = None
            self.context = None
            self.page = None
            self.client = None   
            self.browser = None
            self.playwright = None
        except Exception as e:
            self.log_error(f"退出浏览器异常: {e}")
    
    def _start_game(self) -> bool:
        """启动游戏"""
    
        try:
            self._stop_game()
            self._create_browser(headless=self.cfg.browser_headless_enable)
            
            # 检测登录状态
            while not self._check_login():
                self.log_info("未登录")
                
                # 如果是 headless，则以非 headless 模式重启启动让用户登录
                if self.cfg.browser_headless_enable:
                    self._restart_browser(headless=False)
                    
                self.log_info("请在浏览器中完成登录操作")
                
                # 循环检测用户是否登录
                while not self._check_login():
                    sleep(2)
                    
                self.log_info("检测到登录成功")
                
                # 如果为 headless 模式，则重启浏览器回到 headless 模式
                if self.cfg.browser_headless_enable:
                    if self.cfg.browser_cookies_enable:
                        self._save_cookies()
                    self._restart_browser(headless=True)
            
            if self.cfg.browser_cookies_enable:
                self._save_cookies()
            self._click_enter_game()
            if not self._wait_in_queue(int(self.cfg.cloud_game_max_queue_time) * 60):
                return False
            
            self.log_info("云游戏启动成功")
            return True 
        except Exception as e:
            self.log_error(f"云游戏启动失败: {e}")
            self._try_dump_page()
            return False
    
    def run_in_playwright_thread(self, func, *args, **kwargs):
        """sync playwright 只允许一个线程来操作，相关的任务都须通过这个函数执行"""
        future = {"event": threading.Event()}
        self.playwright_th_que.put((func, args, kwargs, future))
        future["event"].wait()

        if "exception" in future:
            raise future["exception"]

        return future["result"]
        
    def get_window_handle(self) -> int:
        """查找浏览器的 HWND"""
        if self.hwnd and not self.page.is_closed():
            return self.hwnd
        elif self.page.is_closed():
            return 0
        
        target_pid = None

        # 查找浏览器的 PID
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                if proc.info['cmdline'] and any(self.BROWSER_TAG in arg for arg in proc.info['cmdline']):
                    target_pid = proc.pid
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if target_pid is None:
            return 0

        # 查找浏览器的 HWND
        hwnds = []
        def callback(hwnd, _):
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == target_pid and win32gui.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
        win32gui.EnumWindows(callback, None)
        self.hwnd = hwnds[0] if hwnds else 0
        
        return self.hwnd

    def switch_to_game(self) -> bool:
        if self.cfg.browser_headless_enable:
            self.log_warning("当前为无窗口模式，无法将游戏切换到前台")
            return False
        else:
            return super().switch_to_game()
        
    def get_input_handler(self):
        from module.automation.browser_input import BrowserInput
        return BrowserInput(cloud_game=self, logger=self.logger)

    def take_screenshot(self) -> bytes:
        return self.run_in_playwright_thread(self._take_screenshot)

    def stop_game(self) -> bool:
        return self.run_in_playwright_thread(self._stop_game)

    def start_game(self) -> bool:
        return self.run_in_playwright_thread(self._start_game)