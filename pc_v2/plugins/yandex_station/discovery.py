import ipaddress
import socket

class SpeakerDiscovery:
    def __init__(self):
        self.found_devices = {}

    def remove_service(self, zeroconf, type, name):
        pass

    def update_service(self, zeroconf, type, name):
        pass

    def add_service(self, zeroconf, type, name):
        try:
            info = zeroconf.get_service_info(type, name)
            if info:
                # Получаем все IPv4 адреса устройства
                addresses = [str(ipaddress.ip_address(addr)) for addr in info.addresses if len(addr) == 4]
                props = {k.decode(): v.decode() if isinstance(v, bytes) else v for k, v in info.properties.items()}
                device_id = props.get("deviceId")
                if device_id and addresses:
                    self.found_devices[device_id] = {
                        "ip": addresses[0], 
                        "platform": props.get("platform"), 
                        "name": name.split(".")[0]
                    }
        except:
            pass

def get_all_interfaces():
    """Возвращает список всех IPv4 адресов локальных интерфейсов, исключая проблемные"""
    interfaces = []
    try:
        # Пытаемся получить все адреса через socket
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            if info[0] == socket.AF_INET: # Только IPv4
                ip = info[4][0]
                if ip.startswith("127."): continue
                # Исключаем типичные Docker/vEthernet подсети, которые часто вызывают WinError 59
                if ip.startswith("172.17.") or ip.startswith("172.18.") or ip.startswith("172.19."):
                    continue
                interfaces.append(ip)
    except:
        pass
    
    # Если ничего не нашли, попробуем стандартный способ
    if not interfaces:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            interfaces.append(s.getsockname()[0])
            s.close()
        except:
            pass
            
    return list(set(interfaces))
