
from pyModbusTCP.client import ModbusClient

class MODBUS():
    # REF: https://pymodbus.readthedocs.io/en/latest/readme.html
    def __init__(self,ip,port):
        print ("Modbus initializing")
        # Connect to Client
        self.client = ModbusClient(host=ip,port=port,unit_id=1, auto_open=True)  # Always connect 
        self.ip = ip
        self.port = port
    
    def __del__(self):
        #self.client.close()
        pass
    
    def connection_check(self):
        if not self.client.is_open():
            if not self.client.open():
                print ("Unable to connect to %s:%d" % (self.ip, self.port))
                raise "Unable to connecto to PLC controller"
        return True
    
    def refresh(self):
        #pull from modbus
        pass
    
    def send(self):
        print ("Sending")

    def read_coil(self,addr):
        self.connection_check()
        print ("Reading")
        return self.client.read_coils(addr,1)

    def write_coil(self,addr,value):
        self.connection_check()
        print ("Writing")
        responce = self.client.write_single_coil(addr,value)
        return responce
        
    def read_reg(self,addr):
        self.connection_check()
        response =  self.client.read_holding_registers(addr,1)
        print ("Modbus read_reg responce: %r" % response)
        return response
    
    def write_reg(self,addr,val):
        self.connection_check()
        print("Modbus write reg value: %r" % val)
        return self.client.write_single_register(addr, val)

class BIT():
    def __init__(self,addr,modbus):
        self.addr = addr -1
        self.value = 0
        self.mb = modbus
    
    def set(self):
        self.value = 1
        return self.mb.write_coil(self.addr, 1)
    
    def clear(self):
        self.value = 0
        self.mb.write_coil(self.addr, 0)

    def write(self, value):
        self.value = value
        self.mb.write_coil(self.addr, value)

    def read(self):
        self.value = self.mb.read_coil(self.addr)
        #print ("BIT Val: %r" % self.value)
        return self.value

class REGISTER():
    def __init__(self,addr,modbus):
        self.addr = addr -1
        self.value = 0
        self.mb = modbus
    
    def write(self,value):
        self.value = value
        self.mb.write_reg(self.addr, value)
    
    def read(self):
        self.value = self.mb.read_reg(self.addr)
        #print ("REG Val: %r" % self.value)
        return self.value
    
    
class HBW():
    def __init__(self,modbus):
        self.Task1 =        BIT(101,modbus)
        self.slot_x =       REGISTER(105,modbus)
        self.slot_y =       REGISTER(106,modbus)
        self.status_ready = BIT(130,modbus)
        self.status_fault = BIT(180,modbus)
        self.fault_code   = REGISTER(181,modbus)

    def IsReady(self):
        return self.status_ready.read()
    
    def StartTask1(self,x,y):
        #self.write_reg(self.slot_x.addr, x)
        #self.write_reg(self.slot_y.addr, y)
        # wait or verify
        #self.write_coils(self.Task1.addr, 1)
        self.slot_x.write(x)
        self.slot_y.write(y)
        # wait or verify
        #Set task one and clear it (simuler to pressing HMI button)
        self.Task1.set()
        self.Task1.clear()
        return 1
        
class MPO():
    def __init__(self,modbus):
        self.status_ready = BIT(50,modbus)
        self.status_flag1 = BIT(51,modbus)
        self.status_flag2 = BIT(52,modbus)
        self.Task1 =        BIT(53,modbus)
        self.Task2 =        BIT(54,modbus)

    def IsReady(self):
        return self.status_ready.read()
    
    def StartTask1(self):
        self.Task1.set()
        return 1
class SSC():
    def __init__(self,modbus):
        self.GLED = BIT(60,modbus)
        self.YLED = BIT(61,modbus)
        self.RLED = BIT(62,modbus)

    def LEDclear(self):
        self.GLED.clear()
        self.YLED.clear()
        self.RLED.clear()
    
    def LEDset(self,g,y,r):
        # No input validation. g,y,r shoud be 1 or 0
        if g:
            self.GLED.set()
        else:
            self.GLED.clear()

        if y:
            self.YLED.set()
        else:
            self.YLED.clear()
        
        if r:
            self.RLED.set()
        else:
            self.RLED.clear()

class FACTORY():
    def __init__(self, ip, port):
        self.mb = MODBUS(ip, port)
        self.hbw = HBW(self.mb)
        self.mpo = MPO(self.mb)
        self.ssc = SSC(self.mb)
    
    def status(self):
        return "We're working on it. Please wait"
    
    def order(self):
        pass
    
    def restock(self):
        pass


factory = FACTORY(ip="192.101.98.246",port=502)

factory.order()
factory.status()
factory.restock()
'''
# Quick test object to validate modbus communications
c = MODBUS("129.101.98.246", 502)
b = BIT(101, c)
v = REGISTER(101,c)

b.set()
b.read()
b.clear()
print(b.read())

v.write(5)
v.read()
v.write(2)
print(v.read())
'''

if __name__ == '__main__':
    mb = MODBUS('129.101.98.246', 502)
    # mb = simbus() # Simulator

    hbw = HBW(mb)
    mpo = MPO(mb)
    ssc = SSC(mb)

    #hbw.Reset()
    hbw.IsReady()
    #hbw.IsFault()
    
    if hbw.IsReady():
        hbw.StartTask1(1,2)
    '''
    if mpo.IsReady():
        mpo.StartTask1()
    '''
    # Control/read a bit directly
    #hbw.slot_x.write(5)
    #val = hbw.status_flag1.read()
    '''
    ssc.LEDset(1,0,1)
    ssc.LEDclear()
    ssc.GLED.set()
    '''