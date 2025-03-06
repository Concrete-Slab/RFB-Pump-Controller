import time
class Timer:
    """Simple class used to ensure certain operations are only performed after a certain period."""

    def __init__(self,pause_time):
        self.__pause_period = pause_time
        self.__previous_time = time.time()

    def check(self):
        """Check if time greater than the pause period has elapsed since last reset"""
        return (time.time() - self.__previous_time) >= self.__pause_period
    
    def reset(self):
        """Reset the timer"""
        self.__previous_time = time.time()