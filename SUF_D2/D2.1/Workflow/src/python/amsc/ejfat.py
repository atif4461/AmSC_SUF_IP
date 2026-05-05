
import e2sar_py


class EjfatSender:
    def __init__(self, ejfat_uri: str, event_source_id=0):
        result = e2sar_py.EjfatURI.get_from_string(ejfat_uri, e2sar_py.EjfatURI.TokenType.instance)
        if result.has_error():
            print("Bad EJFAT_URI: ", result.error())
        self._ejfat_uri = result.value()
        self._event_source_id = 0

    def connect(self):
        print("Connecting EJFAT sender...")
        VALIDATE = False
        USE_IPV6 = False
        USE_HOST_ADDRESS = False

        self._manager = e2sar_py.ControlPlane.LBManager(self._ejfat_uri, VALIDATE, USE_HOST_ADDRESS)
        result = self._manager.add_sender_self(USE_IPV6)

        if result.has_error():
            print("Error registering as sender: ", result.error().message)
            print("Hint: Are you running this on the testbed login node? There's no network path")
            exit(1)

        data_id = self._event_source_id

        flags = e2sar_py.DataPlane.Segmenter.SegmenterFlags()
        flags.useCP = True
        flags.dpV6 = USE_IPV6
        flags.numSendSockets = 4

        self._segmenter = e2sar_py.DataPlane.Segmenter(
            self._ejfat_uri,
            data_id,
            self._event_source_id,
            flags
        )

        self._segmenter.OpenAndStart()
        print("... done")

    def disconnect(self):
        print("Disconnecting EJFAT sender...")
        self._segmenter.stopThreads()
        print("... done")


    def send(self, data:bytes, event_nr=None):
        #res = self._segmenter.sendEvent(data, len(data))
        res = self._segmenter.addToSendQueue(data, len(data))
        if res.has_error():
            print("Error:", res.error())


class EjfatReceiver:

    def __init__(self, name, ejfat_uri, input_port, thread_count=1):

        result = e2sar_py.EjfatURI.get_from_string(ejfat_uri, e2sar_py.EjfatURI.TokenType.instance)
        if result.has_error():
            print("Bad EJFAT_URI: ", result.error())
        self._ejfat_uri = result.value()

        self._name = name
        self._input_port = input_port
        self._thread_count = thread_count

        self._flags = e2sar_py.DataPlane.Reassembler.ReassemblerFlags()
        self._flags.useCP = True
        self._flags.validateCert = False
        self._flags.eventTimeout_ms = 3000


    def connect(self):
        print("Connecting EJFAT receiver...")
        # Create the reassembler
        self._reassembler = e2sar_py.DataPlane.Reassembler(
            self._ejfat_uri,
            self._input_port,
            self._thread_count,
            self._flags
        )

        print("    data_ip=", self._reassembler.get_dataIP())
        print("    port_range=", self._reassembler.get_portRange())
        print("    recv_ports=", self._reassembler.get_recvPorts())

        # Register worker
        print(f"Registering receiver '{self._name}'...")
        result = self._reassembler.registerWorker(self._name)
        if result.has_error():
            print("Error registering as receiver: ", result.error().message)
            exit(1)

        # Fire up the reassembler
        print("Launching reassembler...")
        self._reassembler.OpenAndStart()
        print("... done")


    def disconnect(self):
        print("Disconnecting EJFAT receiver...")

        print("    Deregistering worker...")
        self._reassembler.deregisterWorker()

        print("    Joining threads...")
        self._reassembler.stopThreads()

        print("... done")

    def recv(self, wait_ms=3000):
        return self._reassembler.recvEventBytes(wait_ms)




