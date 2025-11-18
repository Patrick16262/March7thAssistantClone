from abc import ABC, abstractmethod

class InputBase(ABC):

    @abstractmethod
    def mouse_click(self, x, y):
        pass

    @abstractmethod
    def mouse_down(self, x, y):
        pass

    @abstractmethod
    def mouse_up(self):
        pass

    @abstractmethod
    def mouse_move(self, x, y):
        pass

    @abstractmethod
    def mouse_scroll(self, count, direction=-1, pause=True):
        pass

    @abstractmethod
    def press_key(self, key, wait_time=0.2):
        pass

    @abstractmethod
    def secretly_press_key(self, key, wait_time=0.2):
        pass

    @abstractmethod
    def press_mouse(self, wait_time=0.2):
        pass

    @abstractmethod
    def secretly_write(self, text, interval = 0.1):
        pass