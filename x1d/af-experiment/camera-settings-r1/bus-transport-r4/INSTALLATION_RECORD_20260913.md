# bus-transport-r4 实机装载与读取前基线

用户将本轮 AF 实机执行权交给本任务后，本任务独占执行；主任务与回放任务未并发访问设备。

诊断包 SHA-256：`88e2293c39d7b916c9f67cc64f9f08ee35720f0ef79276abc1ee72b14ab9608d`。实际核对当前 r5 manifest 后完成传包和安装，安装结果为 `0 / af-bus-r4-ready`。GUI PID 保持 1368；AF RAM 写入、自动 query/apply、拍摄、对焦、闪光和照片读取均为 0。通信服务按已审查入口切换，所有 USB 句柄已关闭。

| 阶段 | 本目录内证据 | 请求数 | 结果 |
| --- | --- | ---: | --- |
| stage | [stage.json](build/sessions/af-bus-r4-stage-20260912T193644762822Z/stage.json) | 151 | staged=true，failed=false，allHandlesClosed=true |
| apply | [result.json](build/sessions/af-bus-r4-apply-20260912T193704354043Z/result.json) | 7 | completed=true，failed=false，allHandlesClosed=true |
| 读取前观察 | [observation.json](build/sessions/af-bus-r4-observe-20260912T193713915145Z/observation.json)、[匿名计数](build/sessions/af-bus-r4-observe-20260912T193713915145Z/0000.json) | 9 | observed=true，failed=false，allHandlesClosed=true |

新 bus 基线：queries=0、applies=0、uartaccept=0、farm=0、expired=0。transport：calls=27、private=0、returned=0、queue=27、serialtx=197、serialrx=0、receive=168、rxowner=168、rx784=0、uartparse=0。普通流量已触发实际 prepacked 包装函数和 ReceiveMessage observer；serialrx=0 不能解读为原厂无接收。

GUI 保留之前的 queries=15、applies=0、replies=0、timeouts=15、edits=13，paused=1；采样时 shown=0。尚未观察用户在新诊断版上读取。

当前只确认诊断版装载成功，**配置读取超时尚未定位，真实 query/save 尚未验收**。等待用户手动触发一次读取后比较计数；进入页面若已触发读取，则无需额外重复点击。原 r5、bus3 与本版冻结源码、包、validation 均保持不变。
