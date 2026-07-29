import serial
import time
import struct

class MySerial:
    def __init__(self, port, baudrate=115200, timeout=1):
        """
        初始化串口
        :param port: 串口端口，如 'COM1' 或 '/dev/ttyAMA0'
        :param baudrate: 波特率，默认115200
        :param timeout: 超时时间，默认1秒
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.is_open = False
    
    def open(self):
        """
        打开串口
        :return: 成功返回True，失败返回False
        """
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            self.is_open = True
            print(f"串口 {self.port} 打开成功")
            return True
        except Exception as e:
            print(f"串口打开失败: {str(e)}")
            self.is_open = False
            return False
    
    def send_data(self, data):
        """
        发送数据
        :param data: 要发送的数据
        :return: 成功返回True，失败返回False
        """
        if not self.is_open or self.ser is None:
            print("串口未打开")
            return False
        
        try:
            self.ser.write(data.encode('utf-8'))
            return True
        except Exception as e:
            print(f"发送数据失败: {str(e)}")
            return False
    
    def send_deta(self, deta_x, deta_y):
        """
        发送偏差值（二进制协议）
        :param deta_x: x方向偏差值（像素）
        :param deta_y: y方向偏差值（像素）
        :return: 成功返回True，失败返回False

        协议格式（11字节）：
        [0xAA][0x55][dx(float,4字节)][dy(float,4字节)][校验和(1字节)]
        """
        if not self.is_open or self.ser is None:
            print("串口未打开")
            return False

        try:
            # 构建数据包
            header1 = 0xAA
            header2 = 0x55

            # 将 float 转换为小端序字节
            dx_bytes = struct.pack('<f', deta_x)
            dy_bytes = struct.pack('<f', deta_y)

            # 计算校验和（字节2-9的累加和，取低8位）
            checksum = sum(dx_bytes + dy_bytes) & 0xFF

            # 组装完整数据包
            packet = bytes([header1, header2]) + dx_bytes + dy_bytes + bytes([checksum])

            # 发送数据
            self.ser.write(packet)
            return True
        except Exception as e:
            print(f"发送数据失败: {str(e)}")
            return False
    
    def close(self):
        """
        关闭串口
        """
        if self.is_open and self.ser is not None:
            try:
                self.ser.close()
                self.is_open = False
                print(f"串口 {self.port} 关闭成功")
            except Exception as e:
                print(f"串口关闭失败: {str(e)}")
    
    def __del__(self):
        """
        析构函数，自动关闭串口
        """
        self.close()