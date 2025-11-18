import os
import sys
# 将当前工作目录设置为程序所在的目录，确保无论从哪里执行，其工作目录都正确设置为程序本身的位置，避免路径错误。
os.chdir(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)else os.path.dirname(os.path.abspath(__file__)))

import pyuac

#TODO DEBUG
# if not pyuac.isUserAdmin():
#     try:
#         pyuac.runAsAdmin(False)
#         sys.exit(0)
#     except Exception:
#         sys.exit(1)

import atexit
import base64

from module.config import cfg
from module.logger import log
from module.notification import notif
from module.ocr import ocr
from module.cloud import cloud_game

import tasks.game as game
import tasks.reward as reward
import tasks.challenge as challenge
import tasks.tool as tool
import tasks.version as version

from tasks.daily.daily import Daily
from tasks.daily.fight import Fight
from tasks.power.power import Power
from tasks.weekly.universe import Universe
from tasks.daily.redemption import Redemption


def first_run():
    if not cfg.get_value(base64.b64decode("YXV0b191cGRhdGU=").decode("utf-8")):
        log.error("首次使用请先打开图形界面 March7th Launcher.exe")
        input("按回车键关闭窗口. . .")
        sys.exit(0)


def run_main_actions():
    while True:
        version.start()
        game.start()
        reward.start_specific("dispatch")
        Daily.start()
        reward.start()
        game.stop(True)


def run_sub_task(action):
    game.start()
    sub_tasks = {
        "daily": lambda: (Daily.run(), reward.start()),
        "power": Power.run,
        "fight": Fight.start,
        "universe": Universe.start,
        "forgottenhall": lambda: challenge.start("memoryofchaos"),
        "purefiction": lambda: challenge.start("purefiction"),
        "apocalyptic": lambda: challenge.start("apocalyptic"),
        "redemption": Redemption.start
    }
    task = sub_tasks.get(action)
    if task:
        task()
    game.stop(False)


def run_sub_task_gui(action):
    gui_tasks = {
        "universe_gui": Universe.gui,
        "fight_gui": Fight.gui
    }
    task = gui_tasks.get(action)
    if task and not task():
        input("按回车键关闭窗口. . .")
    sys.exit(0)


def run_sub_task_update(action):
    update_tasks = {
        "universe_update": Universe.update,
        "fight_update": Fight.update
    }
    task = update_tasks.get(action)
    if task:
        task()
    input("按回车键关闭窗口. . .")
    sys.exit(0)


def run_notify_action():
    notif.notify(cfg.notify_template['TestMessage'], "./assets/app/images/March7th.jpg")
    input("按回车键关闭窗口. . .")
    sys.exit(0)
    
def get_disclaimer_text():
    RED = "\033[31m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"

    parts = [
        f"{RESET}===================================================={RESET}",
        f"{RESET}====================  免责声明  ===================={RESET}",
        f"{RESET}====================================================\n{RESET}",

        f"{RED}本程序为完全免费、开源项目。{RESET}",
        f"{RESET}如果你为本程序付了钱，请立即退款！{RESET}\n",

        f"{RESET}本项目因倒卖行为受到严重威胁，请勿支持倒卖！{RESET}",
        f"{RESET}在闲鱼等平台，有人以 4000+ 的价格倒卖本软件。{RESET}",
        f"{RESET}你付给倒卖者的每一分钱都会让开源自动化更艰难。{RESET}",
        f"{RED}如已购买，请凭此提示截图要求退款，并举报该商家。\n{RESET}",

        f"{RESET}本软件未授权任何个人或机构以任何方式出售。{RESET}",
        f"{RESET}本软件仅用于学习与交流，不保证任何结果。{RESET}",
        f"{RESET}使用本软件产生的一切后果均由使用者自行承担。\n{RESET}",

        f"{RESET}===================================================\n{RESET}",

        f"{YELLOW}根据米哈游《崩坏：星穹铁道》公平游戏宣言：{RESET}",
        f"{RESET}- \"严禁使用外挂、加速器、脚本等破坏公平性的第三方工具。\"{RESET}",
        f"{RESET}- \"一经发现，官方将根据违规程度采取扣除收益、冻结账号、永久封禁等措施。\"{RESET}",

        f"{RESET}\n==================================================={RESET}",
    ]

    return "\n".join(parts)


def main(action=None):
    first_run()
    log.info("\n" + get_disclaimer_text())
    retry_times = 0
    limit = int(cfg.on_failure_retry_limit)

    while True:
    # 完整运行
        try:
            if action is None or action == "main":
                run_main_actions()

            # 子任务
            elif action in ["daily", "power", "fight", "universe", "forgottenhall", "purefiction", "apocalyptic", "redemption"]:
                run_sub_task(action)

            # 子任务 原生图形界面
            elif action in ["universe_gui", "fight_gui"]:
                run_sub_task_gui(action)

            # 子任务 更新项目
            elif action in ["universe_update", "fight_update"]:
                run_sub_task_update(action)

            elif action in ["screenshot", "plot"]:
                tool.start(action)

            elif action == "game":
                game.start()

            elif action == "notify":
                run_notify_action()

            else:
                log.error(f"未知任务: {action}")
                input("按回车键关闭窗口. . .")
                sys.exit(1)

            break
        except Exception as e:
            if retry_times >= limit:
                raise e
            log.warning(f"发生错误，正在重启整个任务：{e}")
            retry_times = retry_times + 1
            notif.notify(cfg.notify_template['FailureRetry'].format(error=e, times=retry_times, limit=limit))


# 程序结束时的处理器
def exit_handler():
    """注册程序退出时的处理函数，用于清理OCR资源."""
    ocr.exit_ocr()


if __name__ == "__main__":
    try:
        atexit.register(exit_handler)
        main(sys.argv[1]) if len(sys.argv) > 1 else main()
    except KeyboardInterrupt:
        log.error("发生错误: 手动强制停止")
        if not cfg.exit_after_failure:
            input("按回车键关闭窗口. . .")
        sys.exit(1)
    except Exception as e:
        log.error(cfg.notify_template['ErrorOccurred'].format(error=e))
        notif.notify(cfg.notify_template['ErrorOccurred'].format(error=e))
        import traceback
        traceback.print_exc() #TODO debug
        if not cfg.exit_after_failure:
            input("按回车键关闭窗口. . .")
        sys.exit(1)
