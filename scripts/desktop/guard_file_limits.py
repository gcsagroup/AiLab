"""验收守卫的文件句柄耗尽重试；调用者必须在持锁期间使用。

只处理 EMFILE/ENFILE。等待没有超时，避免资源短缺触发退出并释放保护锁。
该工具不能补回观察缺口，也不把重试成功视为原生验收通过。
"""

import errno
import time


def retry_file_limit(operation, failures, *, sleep=time.sleep):
    """保留有限大小的故障计数，资源恢复后重试同一操作。

    operation 须可安全重试，例如读取、原子替换心跳或幂等恢复；不能用来
    重试模型执行、追加业务记录等不可重复操作。日志失败不再触发日志写入。
    """
    while True:
        try:
            return operation()
        except OSError as exc:
            if exc.errno not in (errno.EMFILE, errno.ENFILE):
                raise
            name = errno.errorcode[exc.errno]
            failures[name] = failures.get(name, 0) + 1
            sleep(0.5)


def wait_for_guard_exit(probe, finish_requested, heartbeat, failures, *, sleep=time.sleep):
    """直到收到退出要求且确认 App 已停止；探测失败绝不等价于停止。"""
    while True:
        failures_before = failures.copy()
        requested = retry_file_limit(finish_requested, failures, sleep=sleep)
        active = retry_file_limit(probe, failures, sleep=sleep)
        retry_file_limit(lambda: heartbeat(requested, active), failures, sleep=sleep)
        # 重试可能持续很久；不能用等待前的“已停止”快照决定释放锁。
        if failures != failures_before:
            continue
        if requested and not active:
            return
        sleep(0.5)
