---
title: linux的信号同步与异步笔记
categories:
  - Technology
  - Development
date: 2022-11-25 10:08:09
tags: 
  - linux
  - signal
---

昨天和同事在讨论安卓ANR的SIGQUIT信号处理时，有以下一些疑惑：
- blocked signal是什么意思，有什么意义，是针对进程的还是线程的
- pthread_sigmask是针对当前线程还是进程的
- 关于sigwait的线程，sigwait等待的signal是blocked还是unblocked，或者都可以
- 如何一个signal handler和sigwait都可以处理一个signal，那谁先接收到该信号

接下来每个小节会按顺序说明这几个问题。

> 因为blocked和pending翻译起来有点别扭，所以相关专业词汇就直接用英文描述了。

## blocked signal

blocked signal简单理解就是被中断的信号。不允许这些信号被信号处理器处理。

blocked signal是针对线程的（以线程为对象）。

其作用在于防止某些线程处理特定信号。

其意义有两个：

- 完成开发者需求：对线程手动设置了signal mask，那么线程不会这些信号，防止错误发生。
- 操作系统的机制：signal handler处理信号A时，信号A会被操作系统设置为blocked signal，即signal handler在处理特定信号时，不会处理相同类别的信号。当signal handler处理完信号A后，信号A会还原为unblocked signal（以上仅针对同一个线程。一个线程的signal handler在处理信号A时，另一个线程也可以使用上述的signal handler去处理信号A）。

## pthread_sigmask是针对当前线程还是进程的

针对线程的，哪个线程调用pthread_sigmask，哪个线程的signal mask会对应改变。

## sigwait等待的signal是blocked还是unblocked，或者都可以

都可以。根据官方文档，sigwait是同步的，当sigwait对应的线程接收到处于pending状态的signal，sigwait返回对应的信号。这里没说处于pending状态的signal是blocked或者unblocked（即线程的sigmask是否包含该信号），通过实验证明，blocked和unblocked都可以。

## 如何一个signal handler和sigwait都处理同一个signal，那谁会接收到该信号

根据实验表明，sigwait会接收到该signal，signal handler不会被执行。

另外，如果signal handler等待SIGINT信号，而sigwait等待SIGQUIT信号，在发送SIGINT后，该线程仍处于sigwait的同步等待状态，signal handler无法执行。