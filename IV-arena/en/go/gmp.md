spawn 
孵化、产卵、派生、创建并启动
spawn 强调的是：这个任务从父级（当前线程）中被孕育出来，并且一诞生就直接进入了待准备运行（Runnable）的状态，交给调度器去处理。

migratable
可迁移的 / 动态流转的
定义：指一个实体（如任务 G 或资源包 P）在运行过程中，可以从一个载体（工人 M1）动态地转移、迁移到另一个载体（工人 M2）上。
在你的模型中：如果一个任务可以在不同工位间流转，它就是 Migratable Task。
注：migrated 是过去分词，表示“已经被迁移的”；表示“具有可迁移属性”要用 migratable。

portable
可移植的 / 跨平台的
定义：指软件代码、程序不需要修改，就可以在不同的操作系统（如 Windows 和 Linux）或不同的硬件（如 Intel 和 ARM）上直接运行。
例子：Go 语言是 portable（可移植）的。但在调度运行期，任务的移动绝对不用这个词。

a dedicated scheduler stack
调度专用栈
在计算机科学中，“专用” 几乎 100% 会被翻译为 Dedicated（字面意思是：奉献的、心无旁骛的、专属的）。
它代表**“排他的、不允许别人占用的、为了特定任务而特设的”**。

Dedicated Server
专用服务器（不和别人共享）。
Dedicated GPU：独显 / 专用显卡（相对核显而言）。
Dedicated Thread：专用线程。
所以，a dedicated scheduler stack 意为：“一个专给调度器使用的专属栈”。

bound to / bind to
绑定

backstage
后台

central control room
总控室

global coordination
全局协调

backing 
在计算机底层，当一个高层抽象（Abstraction）需要一个低层实体来“提供真正的物理支持”时，我们统一用 back (动词) 或 backing (形容词)。
"the runtime thread backing the main OS thread" 意为：“在背后默默支撑、实现、承载着主系统线程的那个运行时线程”

Yield
Linux 内核有一个著名的系统调用就叫 sched_yield()（主动让出 CPU 调度）。
在 Go 中，让出 CPU 的底层函数是 goyield()。

a tight loop or long computation
长循环、长计算
为什么叫 tight（紧）：因为这个循环把 CPU 咬得非常死，CPU 几乎 100% 的时间都卡在这个循环的几行机器码里，进去了就很难出来。

voluntarily calls
主动调用

`time.Sleep` is waiting for its timer to fire
这个“时间到了、触发事件、执行回调”的动作，在计算机硬件、操作系统和 Go 源码中，统一且唯一的动词就是 fire（触发 / 点火）。