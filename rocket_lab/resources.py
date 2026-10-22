"""Memory headroom and cooperative limits for this project's own workers."""
import ctypes
import os
import time


def configure_background_worker():
    os.environ['ROCKET_BACKGROUND_WORKER']='1'
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[name]='1'
    priority='normal'
    if os.name=='nt':
        from ctypes import wintypes
        kernel=ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        if kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000):priority='below normal'
    return dict(threads=1,duty_cycle=.5,priority=priority)


class WorkBudget:
    """Yield wall time without changing simulation dt, rewards or actions."""
    def __init__(self,duty=.5,interval=.05,clock=time.perf_counter,sleep=time.sleep):
        if not 0<duty<=1:raise ValueError('Duty cycle must be within (0,1]')
        self.duty=duty;self.interval=interval;self.clock=clock;self.sleep=sleep;self.started=clock()

    def yield_if_needed(self):
        elapsed=self.clock()-self.started
        if elapsed>=self.interval:
            if self.duty<1:self.sleep(min(.25,elapsed*(1-self.duty)/self.duty))
            self.started=self.clock()


_worker_budget=None
def yield_background_work():
    global _worker_budget
    if os.environ.get('ROCKET_BACKGROUND_WORKER')!='1':return
    if _worker_budget is None:_worker_budget=WorkBudget()
    _worker_budget.yield_if_needed()


def memory_headroom():
    if os.name!='nt':return None
    class MemoryStatus(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                  ('physical_total',ctypes.c_ulonglong),('physical_available',ctypes.c_ulonglong),
                  ('commit_total',ctypes.c_ulonglong),('commit_available',ctypes.c_ulonglong),
                  ('virtual_total',ctypes.c_ulonglong),('virtual_available',ctypes.c_ulonglong),
                  ('extended_available',ctypes.c_ulonglong)]
    status=MemoryStatus();status.length=ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):return None
    return dict(physical_available=int(status.physical_available),commit_available=int(status.commit_available))


def memory_is_low(headroom):
    return headroom is not None and (headroom['physical_available']<2*1024**3 or headroom['commit_available']<4*1024**3)
