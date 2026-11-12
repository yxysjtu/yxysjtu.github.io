---
title: SystemVerilog 基础
date: 2025-10-20
tags: [FPGA]
source: https://shuiyuan.sjtu.edu.cn/t/topic/349293/172
---

## system verilog
### 数据类型
与vhdl非常像的一组，替代wire/reg：
* logic：0/1/x/z
* bit：0/1（用于加快仿真速度）

取代integer的一组（但是可综合，但是不支持x/z）
* byte：int8
* shortint：int16
* int：int32
* longint：int64

剩下不可综合
* real：double
* time：uint64

#### 数组
``` systemverilog
logic [3:0][7:0] register;
assign temp = register[2];
assign register[2] = 8'hff;
assign register[1][1] = 1'b0;

logic [31:0] register1 [0:127];
logic [31:0] register2 [128];

//数组整体赋值
logic [31:0] big_vec [256];
logic [31:0] small_vec [128];
assign small_vec = big_vec[128:255];

//数组聚合赋值
logic [7:0] a, b, c;
logic [7:0] vec [0:3];
assign vec = {8'hff, a, b, c};
```

#### enum, struct, typedef
enum类型与C++中的枚举类型基本相同，这种枚举类型适合在有限状态机中进行使用，以简化代码量。值得注意的是，在使用enum时最好能够规定其类型和宽度，否则编译器会默认其为32位宽的变量：


``` systemverilog
enum logic [1:0] {IDLE, LOOKUP, MISS, REFILL} state, next_state;
enum logic [1:0] {S1=2'b11, S2=2'b00, S3=2'b10} crt, nxt;

typedef enum logic [1:0] {
    IDLE = 2'b00,
    RUN  = 2'b01,
    WAIT = 2'b10
} state_t;

state_t curr_state, next_state;

typedef struct packed {
    logic [7:0] addr;
    logic [7:0] data;
    logic       valid;
} packet_t;

packet_t pkt;

```

### 过程（always）
* `always_comb`：always @(*)
* `always_ff  @(posedge clk)`： always @(posedge clk)

### 接口（interface）
没有接口，模块互连要声明大量信号，以及把大量信号填进模块里，非常麻烦

在顶层定义互连的时候使用interface可以不定义方向，但是interface在模块的端口定义需要定义方向，所以就有了modport

比如**接口定义**
``` systemverilog
interface bus_if(input logic clk);
    logic [7:0] addr;
    logic [31:0] data;
    logic       valid;

    // 定义模块视角
    modport master(input clk, output addr, data, valid);
    modport slave(input clk, input addr, data, valid);
endinterface


```

**在模块中使用**
``` systemverilog
module master(bus_if.master bus);
    always_ff @(posedge bus.clk) begin
        bus.addr  <= 8'h12;
        bus.data  <= 32'hDEADBEEF;
        bus.valid <= 1'b1;
    end
endmodule

module slave(bus_if.slave bus);
    always_ff @(posedge bus.clk) begin
        if (bus.valid) begin
            $display("Received addr=%h data=%h", bus.addr, bus.data);
        end
    end
endmodule

```

**顶层连接**
``` systemverilog
module top;
    logic clk;
    bus_if bus(clk);

    master u_master(bus);
    slave  u_slave(bus);

    // 时钟产生
    initial clk = 0;
    always #5 clk = ~clk;
endmodule

```
### 任务与函数（task, function）
#### function
可复用的组合逻辑

``` systemverilog
//方法1：直接对函数名赋值
function automatic int max(input int a, input int b);
    if (a > b)
        max = a;
    else
        max = b;
endfunction

//方法2：显式 return
function automatic int max(input int a, input int b);
    return (a > b) ? a : b;
endfunction

```

调用：
``` systemverilog
assign bigger = max(a, b);
if (add(a, b) > 10) ...
y = add(x, max(u, v));
```

参数化：
``` systemverilog
function automatic [WIDTH-1:0] reverse_bits #(
    parameter int WIDTH = 8
) (input logic [WIDTH-1:0] data);
    for (int i = 0; i < WIDTH; i++)
        reverse_bits[i] = data[WIDTH-1-i];
endfunction
```

调用：
``` systemverilog
out8  = reverse_bits#(8)(a);
out16 = reverse_bits#(16)({a,a});
```

#### task
常用于验证时驱动测试信号

比如
``` systemverilog
task send_byte(input [7:0] data);
  integer i;
  for (i = 0; i < 8; i++) begin
    tx = data[i];
    #10; // 等10ns发送下一位
  end
endtask

initial begin
  send_byte(8'hA5);
  send_byte(8'h5A);
end

```

驱动总线信号
``` systemverilog
interface bus_if (input logic clk);
    logic [7:0] addr, data;
    logic we, re;

    task automatic write(input logic [7:0] a, input logic [7:0] d);
        @(posedge clk);
        addr <= a;
        data <= d;
        we <= 1;
        @(posedge clk);
        we <= 0;
    endtask
endinterface
```

调用：
``` systemverilog
bus_if bus(clk);

initial begin
    bus.write(8'h10, 8'hA5);
end
```

### 包（package）

``` systemverilog
package my_pkg;

  // 定义常量
  parameter int DATA_WIDTH = 8;

  // 定义类型
  typedef enum logic [1:0] {
    IDLE, RUN, DONE
  } state_t;

  // 定义函数
  function int add(input int a, input int b);
    add = a + b;
  endfunction

endpackage : my_pkg

```
引入
``` systemverilog
import my_pkg::*;  // 导入包中所有定义

module top;
  logic [DATA_WIDTH-1:0] data;
  state_t state;

  initial begin
    data = add(3, 4);
    state = RUN;
  end
endmodule

```
