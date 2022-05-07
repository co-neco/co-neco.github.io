---
title: StackUnwind
date: 2021-07-31 22:42:18
categories: 
 - Technology
 - Reverse
tags: 
 - StackUnwind
---

## StackWalk64(32位)栈回溯原理

### 目标

StackWalk64是用于回溯栈的，32位和64位皆可。本次目标为StackWalk如何回溯32位程序的栈

> 注：
>
> - 本次分析集中于无符号文件，有符号信息的情况将略讲
> - 64位的栈回溯主要依赖程序的Exception Directory数据节，所以相对32位，64位在栈回溯上不用考虑无符号文件(pdb)的问题，因此也不会出现类似32位的问题，比如跳过某一层的函数（在32位无符号文件的情况下）。

### 环境

本次分析以dbghelp.dll,版本为10.0.18362.1139 (WinBuild.160101.0800)。

### 概要流程

![栈回溯大致流程](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/%E6%A0%88%E5%9B%9E%E6%BA%AF%E5%A4%A7%E8%87%B4%E6%B5%81%E7%A8%8B.jpg)

栈回溯使用StackWalk64函数，根据有无符号文件，会分别处理。无论有无符号，都会判断是否是回溯第一层栈。

因为一般情况下没有符号文件， 所以这里只重点分析无符号文件的情况，并在合适的时机提出有符号文件的处理流程。

### 细节流程

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/%E6%A0%88%E5%9B%9E%E6%BA%AF%E7%BB%86%E8%8A%82%E6%B5%81%E7%A8%8B.jpg)

DoDbhUnwind为栈回溯的真正起点，由StackWalk64到DoDbhUnwind的过程都可理解为包装。

重点如下：

- UnwindAndUpdateInternalContext是X86栈回溯的核心函数
- 如果有符号，会交给UnwindInternalContextUsingDiaFrame处理，因为直接有符号了，少了验证等过程，所以该函数就是栈回溯的终点了
- 如果没有符号，会根据栈回溯是否是第一层，走以下路线
  - 第一层：调用UnwindInternalContextUsingEbp，读取ebp的值返回上一层的ebp和eip
  - 第二层或以上：调用UnwindUsingPrologueSummary，解析栈

#### 第一层栈回溯（无符号）

``` c
0:000> k
 # ChildEBP RetAddr  
00 0019e98c 72f92d16 dbghelp!DbsX86StackUnwinder::UnwindInternalContextUsingEbp
01 0019e9ac 72f929ee dbghelp!DbsX86StackUnwinder::DoUnwindUsingInternalContext+0x169
02 0019ea14 72f92925 dbghelp!DbsX86StackUnwinder::UnwindAndUpdateInternalContext+0x7e
03 0019eb44 72f92e5a dbghelp!DbsStackUnwinder::DoDbhUnwind+0x179
04 0019eb74 72f925ea dbghelp!DbsStackUnwinder::DbhUnwind+0x59
05 0019ec90 72f91dd2 dbghelp!PickX86Walk+0x107
06 0019f94c 72f91ba8 dbghelp!DoUnwindStackFrameUsingServices+0xbb
07 0019f998 730a22c9 dbghelp!StackWalkEx+0x1b8
08 0019fb04 00404c1e dbghelp!StackWalk64+0x89
WARNING: Stack unwind information not available. Following frames may be wrong.
09 0019ff24 00406865 cpp_test_ano+0x4c1e
0a 0019ff70 76336359 cpp_test_ano+0x6865
0b 0019ff80 76fb8944 KERNEL32!BaseThreadInitThunk+0x19
0c 0019ffdc 76fb8914 ntdll!__RtlUserThreadStart+0x2f
0d 0019ffec 00000000 ntdll!_RtlUserThreadStart+0x1b
```

回溯第一层栈使用UnwindInternalContextUsingEbp函数，该函数直接从ebp获取第一层栈的ebp和eip。

该函数实现如下：

```c
BOOL DbsX86StackUnwinder::UnwindInternalContextUsingEbp(){
    BOOL result;
    
    this[0xE3] = *(PDWORD)((PBYTE)this[0xE2] + 4); // 0xE2偏移处保存上一层的ebp，0xE3偏移处保存上一层的eip
    this[0xE2] = *this[0xE2];
    if (read memory failed)
        result = TRUE;
    else
        result = FALSE;
    
    return result;
}
```

待UnwindInternalContextUsingEbp返回后，DoUnwindUsingInternalContext函数也直接返回，表示第一层栈已回溯完毕。

> 注：本例只分析ebp回溯的情况，esp回溯的情况（等下周填充）

#### 第二层栈回溯（无符号）

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/%E7%AC%AC%E4%BA%8C%E5%B1%82%E6%A0%88%E5%9B%9E%E6%BA%AF.jpg)

从第二层栈回溯开始，都需要走这样的流程。

SearchForReturnAddress获取ebp和eip是通过评定分数来确认的，分数最高的视为上一层的ebp，并从中获取本层的ebp和eip。

分数由ComputeScoreForReturnAddress获取（算法请参考下一小节），鉴定方式如下：

- 如果返回值为0xFFFF，则视为最高分数，直接返回
- 如果返回值不为0xFFFF，则判断返回值与之前的返回值谁大，如果大于，则更新，否则不更新。之后继续循环，直到循环次数超过0x42次（从0开始计数）。

> 注：前三次base ebp不变，只是传给ComputeScoreForReturnAddress的其中一个参数会变（根据这个参数，获取的分数会不一样）

#### 获取分数的算法

- 上层通过call imm16/imm32（E8 xxxx/E8 xxxxxxxx），根据ComputeScoreForReturnAddress的参数(通常最高为0x9000)
- 上层通过call reg16/reg32(FF xx)，根据ComputeScoreForReturnAddress的参数，获取分数（通常最高为0xA000）
- 上层通过call [mem16/mem32]（FF15[xxxxxxxx]/FF15[xxxx]）,根据ComputeScoreForReturnAddress的参数，获取分数（通常最高为0xA000）

> 注：
>
> - 如果以上三种情况都不是，那base ebp将持续加4，继续寻找。这样的结果就是跳过调用栈中不规则的调用层。
> - 算法的详细讲解请参考第五节。

#### 被忽略的不规则调用层

- jmp指令，jmp指令是0xEB or 0xE9 or 0xFF25，所以会被跳过
- 通过esp调节堆栈的函数（如果没有符号文件）

### 细节讲解

#### DbsStackUnwinder::DoDbhUnwind函数

DoDbhUnwind函数为回溯栈的核心，每执行一次DoDbhUnwind函数，代表回溯完一层栈。

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/DoDbhUnwind.png)

上图为DoDbhUnwind的大致流程，重点如下：

- nonFirstStackFlag(**\*(DWORD \*)(a2 + 0x7C)**)的含义：

  - 第一层栈时，该字段为0，只执行105行的UnwindAndUpdateInternalContext，回溯一次
  - 第二层或以上时，该字段为1，执行78行和105行的UnwindAndUpdateInternalContext，回溯两次

  根据4.1节和4.2节的描述，我们知道第一层栈回溯是通过UnwindInternalContextUsingEbp实现的，第二层或之后的栈回溯是通过UnwindUsingPrologueSummary实现的，选择执行哪条分支是通过nonFirstStackFlag来判断的，如下图：

  ![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/nonFirstStackFlag.png)

  > 注：第二层或以上，为何要调用两次UnwindAndUpdateInternalContext将在之后下一小节讲解。

- ImportPreviousFrameSummary函数

  **说明该函数之前，需要补充一点背景，如下：**

  从回溯第二层或以上的栈开始，都会调用UnwindAndUpdateInternalContext两次，每调用一次该函数，都能回溯一层栈。

  可能大家会有疑问了，上文提及“每执行一次DoDbhUnwind函数，代表回溯完一层栈”，这里DoDbhUnwind调用两次UnwindAndUpdateInternalContext，那不应该是回溯了两层栈吗？

  针对这个问题，请查看文末的附录1的实验，观察StackWalk64返回的CONTEXT（上下文）有何变化。

  根据附录1的实验，能得出以下结论：

  - 在分析第二层或以上的栈时，需要回溯两次才能回溯到真正的函数（context结构体的ebp和eip与待分析的函数差两层）

  根据逆向分析结果，再补充以下结论：

  ![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/%E5%9B%9E%E6%BA%AF%E6%96%B9%E6%B3%95%E7%9B%B8%E5%90%8C.png)

  - Round1由FuncB到FuncC的回溯与Round2由FuncB到FuncC的回溯是一样的

  > 在分析第二层或以上的栈时，context结构体的ebp和eip与待分析的函数差两层的目的是为了获取上一层的栈帧信息（比如Round2的FuncC栈层的信息），这些栈帧信息在内部使用，并反映在DbsStackUnwinder类的一些标志变量中。猜测这些变量会根据情况改变函数的分析流程（比如Round2的FuncD的分析流程）。在接下来的分析中，大家会看到栈回溯的整个过程用到了很多标志变量，来改变比如FuncD函数的分析路径。

  有以上背景后，我们理解了在分析第二层或以上的栈时，为何会调用两次UnwindAndUpdateInternalContext了，接下来回到对ImportPreviousFrameSummary函数的说明。

  在回溯第二层栈时(Round1)，会像Round0一样先从函数A的ebp获取函数A的返回地址（UnwindInternalContextUsingEbp）。又因为只有nonFirstFlag为FALSE时，才会走UnwindInternalContextUsingEbp分支，所以ImportPreviousFrameSummary的其中一个作用就是在第二层栈回溯中，第一次调用UnwindAndUpdateInternalContext时，将nonFirstFlag置为FALSE（注意在第二层或之后的栈回溯，nonFirstFlag都为TRUE）。第二次调用UnwindAndUpdateInternalContext之前，nonFirstFlag会被恢复为TRUE。

#### UnwindAndUpdateInternalContext

回顾第四节的细节流程图，该函数是栈回溯真正功能的起始点。首先执行完初始化之后，会调用UnwindInternalContextUsingDiaFrame，去寻找返回地址（从context.ebp+4地址处获取）的符号文件，如果找到，则直接通过符号文件回溯栈，然后直接从UnwindAndUpdateInternalContext返回，完成该轮的栈回溯。如果没找到，则UnwindInternalContextUsingDiaFrame返回错误0x80004002，之后做无符号的栈回溯（通过ebp），如下图：

![](https://image-hosts.oss-cn-chengdu.aliyuncs.com/reverse/stack_unwind/DoUnwindUsingInternalContext.png)

#### UnwindUsingPrologueSummary

回顾4.2节的第二层栈回溯流程图，该函数先调用CollectFullFunctionInformation和FindStackStateOnFunctionEntry获取一些函数状态信息，之后调用SearchForReturnAddress，通过windows自定义的算法去寻找真正符合要求的返回地址。之后再调用SearchForFramePointer寻找framePointer(帧指针)，不过这个过程往往是直接从ebp读取出新的ebp。

找到ebp和eip之后，将其保存到DbhStackServices类的0x388和0x38C偏移处。到这里，UnwindAndUpdateInternalContext就结束返回了，最后将DbhStackServices类获取到的eip交给STACKFRAME64结构体（StackWalk64提供的参数）。

#### ComputeScoreForReturnAddress(获取分数的算法细节)

```c
// psudo code
int DbsX86HeuristicTool::SearchForReturnAddress(DWORD ebp){
    
    DWORD dwScore = 0;
    BYTE flag[3] = { 0 };
    
    for (int i =0 ;i < 0x42; i++) {
        if (i == 1)
            flag[1] = 1;
        else if (i == 2) {
            flag[1] = 0;
            flag[2] = 1;
        }
        else if (i > 2) {
            ebp = ebp + 4;
        }
        
        DWORD eip = *(DWORD*)(ebp+4);
        DWORD dwComputedScore = ComputeScoreForReturnAddress(eip, &flag);
        if (dwScore ==0xFFFF)
            return 0;
        if (dwComputedScore > dwScore)
            dwScore = dwComputedScore;
    }
    
    return dwScore != 0 ? 1 : 2;
}


DWORD DbsX86HeuristicTool::ComputeScoreForReturnAddress(DWORD eip, PBYTE pFlag){
    DWORD dwScore = 0;
    PVOID pImageBase = NULL;
    DWORD rs = FALSE;
    
    PBYTE content[8] = {0};
    DWORD dwbytesRead = 0;
    rs = ReadMemory(eip - 8, content, 8, &dwbytesRead);
    if (!rs) {
        // After some search, 0xC4C4 may be a invalid opcode.
        if (content[0] == 0xC4 && content[1] == 0xC4 && dwbytesRead==8)
            return 0xFFFF;
    }
    
    dwBytesRead = 0;
    memset(content, 0, 7);
    rs = ReadMemory(eip - 7, content, 7, &dwbytesRead);
    
    if (content[2]==0xE8) {
        //call imm16/imm32（E8 xxxx/E8 xxxxxxxx）
        rs = IsCodeReachableViaDirectCall(...);
        if (!rs)
            // IsCodeReachableViaDirectCall always returns FALSE
            if (pFlag[2] == 1)
                return 0x9000;
        	else
                dwScore = 0x3000;
    }
    
    for (PBYTE pNow = content; pNow - content <7; pNow++) {
        if (pNow == 0xFF && (pNow[1] & 0x30 != 0x10)) {
            if (pNow - content == 1) {
                // call [mem16/mem32] -> FF15[xxxxxxxx]/FF15[xxxx]
            }
            else if (pNow - content == 5) {
                // call reg16/reg32   -> (FF xx)
            }
            else
                continue;
            
            if (pFlag[2] && dwScore <= 0x9000)
                dwScore = 0x9000;
            else if (pFlag[1] && dwScore <= 0xA000)
                dwScore = 0xA000;
            
            if (dwScore < 0x6000)
                dwScore = 0x6000;
            
            break;
        }
    }
    
	return dwScore;
}
```

#### winXP和win10的dbghelp.dll在栈回溯的细微区别

如果在栈回溯时，遇到返回地址不属于任何模块的情况（比如执行的是一段shellcode），winXP和win10的行为如下：

- win10：win10会判断一个标志位是否为0，如果为0，则忽略返回地址，ebp继续加4，然后读取ebp指向的内容，继续解析下一个（参考上一节的算法细节）；如果为1，则继续解析该返回地址，即强制认为这个地址是有效的。

  > 注：这个标志位在DbsX86StackUnwinder类的构造函数被置为1(写死的)，初始化路径为StackWalk64->StackWalkEx->DoUnwindStackFrameUsingServices->New_DbsStackUnwinderhan->DbsX86StackUnwinder。

- winXP：winXP直接视该返回地址无效，ebp继续加4，继续解析下一个。

#### Debug版和Release版程序在栈回溯的区别

debug版的函数通常会预留一部分栈空间，并初始化为0xCC，方便栈溢出的检测，而release版本没有。这个区别导致栈回溯会出现以下区别：

- Debug版：因为栈多出了很多0xCC，所以在寻找正确的返回地址时，可能会达到循环次数的上限，导致栈回溯找不到正确的返回地址，这种情况下，dbghelp（winXP和win10一样）会视最初的ebp+4指向的内容为返回地址，即使该返回地址是无效的。
- Release版：因为栈排布很紧密，所以基本上不存在上述问题。



### 附录：

#### 实验：StackWalk64返回的CONTEXT（上下文）
  - 1.StackWalk64原型（[详情可参考MSDN](https://docs.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-stackwalk64)）：

    ```c
    BOOL IMAGEAPI StackWalk64(
      DWORD                            MachineType,
      HANDLE                           hProcess,
      HANDLE                           hThread,
      LPSTACKFRAME64                   StackFrame,
      PCONTEXT                         ContextRecord,
      PREAD_PROCESS_MEMORY_ROUTINE64   ReadMemoryRoutine,
      PFUNCTION_TABLE_ACCESS_ROUTINE64 FunctionTableAccessRoutine,
      PGET_MODULE_BASE_ROUTINE64       GetModuleBaseRoutine,
      PTRANSLATE_ADDRESS_ROUTINE64     TranslateAddress
    );
    ```

    该函数有两个重要参数，StackFrame和ContextRecord，其中ContextRecord代表当前待分析的环境，重要的参数为ContextRecord.eip和ContextRecord.ebp。

  - 2.StackWalk64的使用：

    ```c
    #define GET_CURRENT_THREAD_CONTEXT(c, contextFlags) \
      do                                                              \
      {                                                               \
        c.ContextFlags = contextFlags;                                \
        __asm    call x                                               \
        __asm x: pop eax                                              \
        __asm    mov c.Eip, eax                                       \
        __asm    mov c.Ebp, ebp                                       \
        __asm    mov c.Esp, esp                                       \
      } while (0)
    
    CONTEXT context;
    memset(&context, 0, sizeof(context));
    context.ContextFlags = CONTEXT_CONTROL;
    GET_CURRENT_THREAD_CONTEXT(context, CONTEXT_CONTROL);
    
    for (size_t i = 0; i < 1024; ++i) {
    	auto ret = StackWalk64(imageType,
    		GetCurrentProcess(),
    		GetCurrentThread(),
    		&frame64,
    		&context,
    		NULL,
    		SymFunctionTableAccess64,
    		SymGetModuleBase64,
    		NULL);
    
    	std::cout << "Round: " << i << "\n";
    #if defined(_M_IX86)
    	std::cout << "context ebp: " << std::hex << context.Ebp << "\n";
    	std::cout << "context eip: " << std::hex << context.Eip << "\n";
    #elif defined(_M_AMD64)
    	std::cout << "context rbp: " << std::hex << context.Rbp << "\n";
    	std::cout << "context rip: " << std::hex << context.Rip << "\n";
    #endif
    	std::cout << "Frame ebp: " << std::hex << frame64.AddrFrame.Offset << "\n";
    	std::cout << "Frame eip: " << std::hex << frame64.AddrReturn.Offset << "\n\n\n";
    
    	if (ret == FALSE || frame64.AddrReturn.Offset == 0) {
    		break;
    	}
    }
    ```

    可知，一般StackWalk64都是循环使用的，直到frame64.AddrReturn.Offset为0，代表回溯完毕。

    每循环一次，context的值会有对应的更新。

  - 3.观察StackWalk64返回的CONTEXT（上下文）：

    - 当前的栈（由windbg打印）

      ```c
      ...
      0b 00daefa4 00a4e4c5 dbghelp!StackWalk64+0x89
      0c 00daf640 00a69ef3 cpp_test_ano+0xfe4c5     //函数A
      0d 00daf714 00aab363 cpp_test_ano+0x119ef3    //函数B
      0e 00daf734 00aab1b7 cpp_test_ano+0x15b363    //函数C
      0f 00daf790 00aab04d cpp_test_ano+0x15b1b7    //函数D
      10 00daf798 00aab3e8 cpp_test_ano+0x15b04d
      11 00daf7a0 76336359 cpp_test_ano+0x15b3e8
      ...
      ```
      
    - 程序输出结果

      ```c
      // 为执行StackWalk64的初始值如下
      // context ebp: daf640
      // context eip: a4e34d
      // Frame ebp: daf640
      // Frame eip: a4e34d
      
      Round: 0
      context ebp: daf640
      context eip: a4e34d
      Frame ebp: daf640
      Frame eip: a69ef3
      
      Round: 1
      context ebp: daf714
      context eip: a69ef3
      Frame ebp: daf714
      Frame eip: aab363
      
      Round: 2
      context ebp: daf734
      context eip: aab363
      Frame ebp: daf734
      Frame eip: aab1b7
      
      Round: 3
      context ebp: daf790
      context eip: aab1b7
      Frame ebp: daf790
      Frame eip: aab04d
      
      Round: 4
      context ebp: daf798
      context eip: aab04d
      Frame ebp: daf798
      Frame eip: aab3e8
      ...
      ```
    
    根据以下数据，有以下结论：
    
    - 第一轮结束后（Round0）
    
      - frame64.ebp和context.ebp并没有更新，还是0xdaf640
      - context.eip并没有更新，还是0xa4e34d
      - fram64.eip更新了，为0xa69ef3，该值是第一层栈的地址，即调用函数A的地址，该地址位于函数B中
    
      > 注：StackWalk64回溯栈时，是根据context.ebp和context.eip来分析的。为了分析第二层栈，context.ebp和context.eip应该对应函数B才对，这样下次调用StackWalk64才能获取函数C是在哪调用函数B的，即fram64.eip。目前context.ebp和context.eip对应的是函数A。
    
    - 第二轮结束后（Round1）
    
      - frame64.ebp和context.ebp都更新了，是0xdaf714
      - context.eip更新了，是0xa4e34d
      - fram64.eip更新了，是0xaab363，该值是第二层栈的地址，即调用函数B的地址，该地址位于函数C中
    
      > 注：context的ebp和eip对应的是函数B，并不是函数C。与下次要获取的函数D差两层
    
    观察之后的层数，其结果与Round1一样。**context的ebp和eip对应的函数与下一次要回溯的函数差两层**。

### 总结

- 本来由来：在栈回溯时，发现release版本的栈回溯会跳过一层函数，这层函数是jmp XXXXXXXX。为了明确何时会跳过函数，所以做了一系列分析，于是有了这篇文章。

- winXP和win10在栈回溯的差异不大，大致流程基本一样（函数的封装有所变化，比如win10的DbsStackUnwinder::DoDbhUnwind函数在winXP是DbsStackUnwinder::DbhUnwind）。因此win7、win8各位也可以类推，找到其栈回溯的大致流程。

- 在栈回溯时，有符号与无符号的执行流程是有差别的。有符号的情况下，UnwindInternalContextUsingDiaFrame(win10下)会读取符号，解析符号，直接返回。如果要分析有符号的情况，各位重点查看这个函数即可（winXP下是DbsX86StackUnwinder::ApplyUnwindInfo）。
- 关于ComputeScoreForReturnAddress的算法，这里简化了参数验证等无关代码，流程上也做了简化。同时这里省略了一些不重要的细节，比如检验是否是热更新代码；检验call [addr A]的情况下，call的地址和addr A是否属于同一个模块。类似这些都属于常规检测，在栈回溯时情况基本相同，可暂时忽略。

- 64位栈回溯在无符号的情况下，会根据Exception Directory数据节的函数信息进行回溯。在分析winXP时，发现dbghelp.dll会缓存一份Exception Directory数据节进行分析，所以对分析模块的Exception Directory数据节下硬件断点，可能断不下来，找不到dbghelp.dll回溯的代码。虽然64位的分析流程和32位完全不同，但主流程是一样的，都会调用\*Unwind函数，然后做一些基础检测，分析call、jmp这些基础操作。
