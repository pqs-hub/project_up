"""
测试模块数据集
包含4类典型Verilog模块：计数器、状态机、ALU、多路复用器
每类5个样本，共20个测试用例
"""


# ============================================================================
# 计数器 (Counter)
# ============================================================================

COUNTER_MODULES = [
    {
        "id": "counter_8bit_simple",
        "type": "counter",
        "spec": "Implement an 8-bit up counter with synchronous reset. When reset is high, count should be 0. Otherwise, count increments by 1 on each clock rising edge.",
        "rtl": """module counter(
    input clk,
    input rst,
    output reg [7:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 8'b0;
        else
            count <= count + 1;
    end
endmodule""",
        "testbench": """module tb;
    reg clk, rst;
    wire [7:0] count;
    
    counter dut(clk, rst, count);
    
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end
    
    initial begin
        rst = 1; #10;
        rst = 0; #100;
        if (count == 8'd10) $display("PASS");
        else $display("FAIL");
        $finish;
    end
endmodule"""
    },
    {
        "id": "counter_4bit_enable",
        "type": "counter",
        "spec": "Implement a 4-bit counter with enable signal. When enable is high, counter increments. When reset is high, counter is cleared.",
        "rtl": """module counter(
    input clk,
    input rst,
    input enable,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'b0;
        else if (enable)
            count <= count + 1;
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "counter_16bit_load",
        "type": "counter",
        "spec": "Implement a 16-bit counter with load capability. When load is high, counter loads data_in. Otherwise it increments.",
        "rtl": """module counter(
    input clk,
    input rst,
    input load,
    input [15:0] data_in,
    output reg [15:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 16'b0;
        else if (load)
            count <= data_in;
        else
            count <= count + 1;
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "counter_down",
        "type": "counter",
        "spec": "Implement an 8-bit down counter. Counter decrements on each clock cycle. Reset to maximum value (255).",
        "rtl": """module counter(
    input clk,
    input rst,
    output reg [7:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 8'hFF;
        else
            count <= count - 1;
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "counter_modulo",
        "type": "counter",
        "spec": "Implement a modulo-10 counter (0 to 9). When count reaches 9, it wraps to 0.",
        "rtl": """module counter(
    input clk,
    input rst,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'b0;
        else if (count == 4'd9)
            count <= 4'b0;
        else
            count <= count + 1;
    end
endmodule""",
        "testbench": ""
    }
]


# ============================================================================
# 状态机 (State Machine)
# ============================================================================

STATE_MACHINE_MODULES = [
    {
        "id": "fsm_2state_simple",
        "type": "state_machine",
        "spec": "Implement a 2-state FSM. State transitions: IDLE->ACTIVE when start=1, ACTIVE->IDLE when done=1. Output 'busy' is high in ACTIVE state.",
        "rtl": """module fsm(
    input clk,
    input rst,
    input start,
    input done,
    output reg busy
);
    reg state;
    parameter IDLE = 1'b0, ACTIVE = 1'b1;
    
    always @(posedge clk) begin
        if (rst)
            state <= IDLE;
        else case (state)
            IDLE: if (start) state <= ACTIVE;
            ACTIVE: if (done) state <= IDLE;
        endcase
    end
    
    always @(*) begin
        busy = (state == ACTIVE);
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "fsm_3state_seq",
        "type": "state_machine",
        "spec": "Implement a 3-state sequential FSM: S0->S1->S2->S0. Transition on each clock cycle.",
        "rtl": """module fsm(
    input clk,
    input rst,
    output reg [1:0] state
);
    parameter S0 = 2'b00, S1 = 2'b01, S2 = 2'b10;
    
    always @(posedge clk) begin
        if (rst)
            state <= S0;
        else case (state)
            S0: state <= S1;
            S1: state <= S2;
            S2: state <= S0;
            default: state <= S0;
        endcase
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "fsm_mealy",
        "type": "state_machine",
        "spec": "Implement a Mealy FSM that detects sequence '101'. Output is high when sequence is detected.",
        "rtl": """module fsm(
    input clk,
    input rst,
    input in,
    output reg out
);
    reg [1:0] state;
    parameter S0 = 2'b00, S1 = 2'b01, S2 = 2'b10;
    
    always @(posedge clk) begin
        if (rst)
            state <= S0;
        else case (state)
            S0: state <= in ? S1 : S0;
            S1: state <= in ? S1 : S2;
            S2: state <= in ? S1 : S0;
        endcase
    end
    
    always @(*) begin
        out = (state == S2) && in;
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "fsm_moore",
        "type": "state_machine",
        "spec": "Implement a Moore FSM with 4 states. Output depends only on current state.",
        "rtl": """module fsm(
    input clk,
    input rst,
    input enable,
    output reg [1:0] out
);
    reg [1:0] state;
    
    always @(posedge clk) begin
        if (rst)
            state <= 2'b00;
        else if (enable)
            state <= state + 1;
    end
    
    always @(*) begin
        out = state;
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "fsm_handshake",
        "type": "state_machine",
        "spec": "Implement a handshake protocol FSM. States: IDLE, REQ, ACK, DONE. Transitions based on req and ack signals.",
        "rtl": """module fsm(
    input clk,
    input rst,
    input req,
    input ack,
    output reg valid,
    output reg ready
);
    reg [1:0] state;
    parameter IDLE = 2'b00, REQ = 2'b01, ACK = 2'b10, DONE = 2'b11;
    
    always @(posedge clk) begin
        if (rst)
            state <= IDLE;
        else case (state)
            IDLE: if (req) state <= REQ;
            REQ: if (ack) state <= ACK;
            ACK: state <= DONE;
            DONE: state <= IDLE;
        endcase
    end
    
    always @(*) begin
        valid = (state == REQ);
        ready = (state == IDLE);
    end
endmodule""",
        "testbench": ""
    }
]


# ============================================================================
# ALU (Arithmetic Logic Unit)
# ============================================================================

ALU_MODULES = [
    {
        "id": "alu_4bit_simple",
        "type": "alu",
        "spec": "Implement a 4-bit ALU with operations: ADD (op=00), SUB (op=01), AND (op=10), OR (op=11).",
        "rtl": """module alu(
    input [3:0] a,
    input [3:0] b,
    input [1:0] op,
    output reg [3:0] result
);
    always @(*) begin
        case (op)
            2'b00: result = a + b;
            2'b01: result = a - b;
            2'b10: result = a & b;
            2'b11: result = a | b;
        endcase
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "alu_8bit_extended",
        "type": "alu",
        "spec": "Implement an 8-bit ALU with ADD, SUB, AND, OR, XOR, NOT operations. Include zero flag output.",
        "rtl": """module alu(
    input [7:0] a,
    input [7:0] b,
    input [2:0] op,
    output reg [7:0] result,
    output reg zero
);
    always @(*) begin
        case (op)
            3'b000: result = a + b;
            3'b001: result = a - b;
            3'b010: result = a & b;
            3'b011: result = a | b;
            3'b100: result = a ^ b;
            3'b101: result = ~a;
            default: result = 8'b0;
        endcase
        zero = (result == 8'b0);
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "alu_comparator",
        "type": "alu",
        "spec": "Implement a 4-bit comparator ALU. Outputs: equal, greater, less.",
        "rtl": """module alu(
    input [3:0] a,
    input [3:0] b,
    output reg equal,
    output reg greater,
    output reg less
);
    always @(*) begin
        equal = (a == b);
        greater = (a > b);
        less = (a < b);
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "alu_shift",
        "type": "alu",
        "spec": "Implement an 8-bit shift ALU. Operations: left shift, right shift, rotate left, rotate right.",
        "rtl": """module alu(
    input [7:0] data,
    input [1:0] op,
    output reg [7:0] result
);
    always @(*) begin
        case (op)
            2'b00: result = data << 1;
            2'b01: result = data >> 1;
            2'b10: result = {data[6:0], data[7]};
            2'b11: result = {data[0], data[7:1]};
        endcase
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "alu_multiplier",
        "type": "alu",
        "spec": "Implement a 4-bit multiplier. Output is 8-bit product.",
        "rtl": """module alu(
    input [3:0] a,
    input [3:0] b,
    output [7:0] product
);
    assign product = a * b;
endmodule""",
        "testbench": ""
    }
]


# ============================================================================
# 多路复用器 (Multiplexer)
# ============================================================================

MUX_MODULES = [
    {
        "id": "mux_4to1",
        "type": "mux",
        "spec": "Implement a 4-to-1 multiplexer. Select signal chooses which input to output.",
        "rtl": """module mux(
    input [3:0] in0,
    input [3:0] in1,
    input [3:0] in2,
    input [3:0] in3,
    input [1:0] sel,
    output reg [3:0] out
);
    always @(*) begin
        case (sel)
            2'b00: out = in0;
            2'b01: out = in1;
            2'b10: out = in2;
            2'b11: out = in3;
        endcase
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "mux_2to1_8bit",
        "type": "mux",
        "spec": "Implement an 8-bit 2-to-1 multiplexer using conditional operator.",
        "rtl": """module mux(
    input [7:0] a,
    input [7:0] b,
    input sel,
    output [7:0] out
);
    assign out = sel ? b : a;
endmodule""",
        "testbench": ""
    },
    {
        "id": "mux_8to1",
        "type": "mux",
        "spec": "Implement an 8-to-1 multiplexer with 3-bit select signal.",
        "rtl": """module mux(
    input [7:0] data0, data1, data2, data3, data4, data5, data6, data7,
    input [2:0] sel,
    output reg [7:0] out
);
    always @(*) begin
        case (sel)
            3'd0: out = data0;
            3'd1: out = data1;
            3'd2: out = data2;
            3'd3: out = data3;
            3'd4: out = data4;
            3'd5: out = data5;
            3'd6: out = data6;
            3'd7: out = data7;
        endcase
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "mux_priority",
        "type": "mux",
        "spec": "Implement a priority multiplexer. If enable[i] is high, output data[i]. Higher index has priority.",
        "rtl": """module mux(
    input [3:0] data0, data1, data2, data3,
    input [3:0] enable,
    output reg [3:0] out
);
    always @(*) begin
        if (enable[3])
            out = data3;
        else if (enable[2])
            out = data2;
        else if (enable[1])
            out = data1;
        else if (enable[0])
            out = data0;
        else
            out = 4'b0;
    end
endmodule""",
        "testbench": ""
    },
    {
        "id": "mux_parametric",
        "type": "mux",
        "spec": "Implement a 4-to-1 multiplexer with parameterized data width (default 8-bit).",
        "rtl": """module mux #(parameter WIDTH = 8) (
    input [WIDTH-1:0] in0, in1, in2, in3,
    input [1:0] sel,
    output reg [WIDTH-1:0] out
);
    always @(*) begin
        case (sel)
            2'b00: out = in0;
            2'b01: out = in1;
            2'b10: out = in2;
            2'b11: out = in3;
        endcase
    end
endmodule""",
        "testbench": ""
    }
]


# 所有测试模块
ALL_TEST_MODULES = (
    COUNTER_MODULES +
    STATE_MACHINE_MODULES +
    ALU_MODULES +
    MUX_MODULES
)


# 核心测试模块（小规模验证用，每类选1个）
CORE_TEST_MODULES = [
    COUNTER_MODULES[0],      # 8-bit counter
    STATE_MACHINE_MODULES[0], # 2-state FSM
    ALU_MODULES[0],          # 4-bit ALU
    MUX_MODULES[0],          # 4-to-1 MUX
]
