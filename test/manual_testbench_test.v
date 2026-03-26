module RefModule (
    input wire clk,
    input wire [3:0] cmd,
    output reg response
);
    always @(posedge clk) begin
        if (cmd == 4'b0001) begin
            response <= 1'b1; // Respond to command 0x01
        end else if (cmd == 4'b0010) begin
            response <= 1'b0; // Respond to command 0x02
        end else begin
            response <= response; // Hold previous response
        end
    end
endmodule
