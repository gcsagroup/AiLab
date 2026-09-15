//! 正常退出前只接受当前请求的一次保存回执；取消或超时均不能授权退出。

use std::{
    sync::mpsc::{self, Receiver, Sender},
    time::{Duration, Instant},
};

#[derive(Default)]
pub(crate) struct ExitPreparation {
    next_id: u64,
    pending: Option<Pending>,
}

struct Pending {
    request_id: u64,
    deadline: Instant,
    sender: Sender<bool>,
    acknowledged: Option<bool>,
}

impl ExitPreparation {
    pub(crate) fn is_pending(&self) -> bool {
        self.pending.is_some()
    }

    pub(crate) fn begin(&mut self, timeout: Duration) -> Option<(u64, Receiver<bool>)> {
        if self.is_pending() {
            return None;
        }
        // 编号通过 JavaScript number 往返，不能超过其精确整数范围。
        let request_id = self
            .next_id
            .checked_add(1)
            .filter(|id| *id <= (1 << 53) - 1)?;
        let (sender, receiver) = mpsc::channel();
        self.next_id = request_id;
        self.pending = Some(Pending {
            request_id,
            deadline: Instant::now() + timeout,
            sender,
            acknowledged: None,
        });
        Some((request_id, receiver))
    }

    pub(crate) fn complete(&mut self, request_id: u64, success: bool) -> bool {
        let Some(pending) = &mut self.pending else {
            return false;
        };
        if pending.request_id != request_id
            || pending.acknowledged.is_some()
            || Instant::now() >= pending.deadline
        {
            return false;
        }
        if pending.sender.send(success).is_err() {
            return false;
        }
        pending.acknowledged = Some(success);
        true
    }

    pub(crate) fn finish(&mut self, request_id: u64, received: Option<bool>) -> Option<bool> {
        let pending = self.pending.as_ref()?;
        if pending.request_id != request_id {
            return None;
        }
        let exit = received == Some(true) && pending.acknowledged == Some(true);
        self.pending = None;
        Some(exit)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn 当前成功回执只授权一次退出() {
        let mut state = ExitPreparation::default();
        let (id, receiver) = state.begin(Duration::from_secs(30)).unwrap();
        assert!(state.is_pending());
        assert!(state.begin(Duration::from_secs(30)).is_none());
        assert!(!state.complete(id + 1, true));
        assert!(state.complete(id, true));
        assert!(!state.complete(id, true));
        assert!(state.is_pending());
        assert_eq!(state.finish(id, receiver.try_recv().ok()), Some(true));
        assert!(!state.is_pending());
        assert_eq!(state.finish(id, Some(true)), None);
        assert!(!state.complete(id, true));
    }

    #[test]
    fn 保存失败不能被第二次成功回执覆盖() {
        let mut state = ExitPreparation::default();
        let (id, receiver) = state.begin(Duration::from_secs(30)).unwrap();
        assert!(state.complete(id, false));
        assert!(!state.complete(id, true));
        assert_eq!(state.finish(id, receiver.try_recv().ok()), Some(false));
        assert!(!state.complete(id, true));
    }

    #[test]
    fn 实际等待超时后拒绝迟到回执并允许重新请求() {
        let mut state = ExitPreparation::default();
        let (old_id, receiver) = state.begin(Duration::from_millis(1)).unwrap();
        let received = receiver.recv_timeout(Duration::from_millis(2)).ok();
        assert_eq!(received, None);
        assert!(!state.complete(old_id, true));
        assert_eq!(state.finish(old_id, received), Some(false));
        let (id, receiver) = state.begin(Duration::from_secs(30)).unwrap();
        assert!(id > old_id);
        assert!(!state.complete(old_id, true));
        assert_eq!(state.finish(old_id, Some(true)), None);
        assert!(state.complete(id, true));
        assert_eq!(state.finish(id, receiver.try_recv().ok()), Some(true));
    }

    #[test]
    fn 发出事件失败取消后不能用旧编号退出() {
        let mut state = ExitPreparation::default();
        let (id, _receiver) = state.begin(Duration::from_secs(30)).unwrap();
        assert_eq!(state.finish(id, None), Some(false));
        assert!(!state.complete(id, true));
        assert_eq!(state.finish(id, Some(true)), None);
    }

    #[test]
    fn 没有真实成功回执或没有收到回执均不能退出() {
        let mut state = ExitPreparation::default();
        let (id, _receiver) = state.begin(Duration::from_secs(30)).unwrap();
        assert_eq!(state.finish(id, Some(true)), Some(false));
        let (id, _receiver) = state.begin(Duration::from_secs(30)).unwrap();
        assert!(state.complete(id, true));
        assert_eq!(state.finish(id, None), Some(false));
    }

    #[test]
    fn 接收端消失不能接受回执() {
        let mut state = ExitPreparation::default();
        let (id, receiver) = state.begin(Duration::from_secs(30)).unwrap();
        drop(receiver);
        assert!(!state.complete(id, true));
        assert_eq!(state.finish(id, None), Some(false));
    }
}
