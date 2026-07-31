#!/usr/bin/env python3
"""
Digital Twin Interactive Probe Script

This script provides an interactive command-line interface to probe, monitor,
and interact with the Digital Twin component for debugging, testing, and
observability purposes.

Features:
- gRPC client for all Digital Twin services (Query, Simulate, Diagnose, Manage)
- NATS client for publishing test events and monitoring messages
- Interactive command-line interface with help system
- Real-time monitoring capabilities
- Standalone with minimal dependencies

Usage:
    python digital_twin_probe.py                    # Start with defaults
    python digital_twin_probe.py --help             # Show detailed help
    python digital_twin_probe.py --grpc-host remote # Connect to remote gRPC
    python digital_twin_probe.py --nats-url nats://remote:4222

Quick Start:
    1. python digital_twin_probe.py --help          # Read detailed usage
    2. python digital_twin_probe.py                 # Start probe
    3. dt-probe> connect all                        # Connect to services
    4. dt-probe> test                               # Run test suite
    5. dt-probe> help                               # List all commands
"""

import asyncio
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import argparse
import cmd
import threading

# Minimal imports - only standard library and essential packages
try:
    import grpc
    from concurrent import futures
except ImportError:
    print("Error: grpcio package required. Install with: pip install grpcio grpcio-tools")
    sys.exit(1)

try:
    import nats
    from nats.aio.client import Client as NATS
except ImportError:
    print("Error: nats-py package required. Install with: pip install nats-py")
    sys.exit(1)

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from polaris.proto import digital_twin_pb2, digital_twin_pb2_grpc
except ImportError:
    print("Error: Could not import Digital Twin protobuf definitions.")
    print("Make sure you're running from the correct directory and protobuf files are generated.")
    sys.exit(1)


class DigitalTwinProbe:
    """Interactive probe for Digital Twin component."""
    
    def __init__(self, grpc_host: str = "localhost", grpc_port: int = 50051, 
                 nats_url: str = "nats://localhost:4222"):
        """Initialize the probe.
        
        Args:
            grpc_host: gRPC server host
            grpc_port: gRPC server port
            nats_url: NATS server URL
        """
        self.grpc_host = grpc_host
        self.grpc_port = grpc_port
        self.nats_url = nats_url
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("dt_probe")
        
        # gRPC components
        self.grpc_channel: Optional[grpc.Channel] = None
        self.grpc_stub: Optional[digital_twin_pb2_grpc.DigitalTwinStub] = None
        
        # NATS components
        self.nats_client: Optional[NATS] = None
        self.nats_connected = False
        
        # Monitoring state
        self.monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.received_messages: List[Dict[str, Any]] = []
        
        # Event loop for async operations
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.loop_thread: Optional[threading.Thread] = None
        
    def start_event_loop(self):
        """Start the asyncio event loop in a separate thread."""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
        
        # Wait for loop to be ready
        while self.loop is None:
            time.sleep(0.01)
    
    def run_async(self, coro):
        """Run an async coroutine from sync context."""
        if self.loop is None:
            self.start_event_loop()
        
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=30)  # 30 second timeout
    
    async def connect_grpc(self) -> bool:
        """Connect to gRPC server."""
        try:
            self.grpc_channel = grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}")
            self.grpc_stub = digital_twin_pb2_grpc.DigitalTwinStub(self.grpc_channel)
            
            # Test connection
            await self.grpc_channel.channel_ready()
            self.logger.info(f"✅ Connected to gRPC server at {self.grpc_host}:{self.grpc_port}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to gRPC server: {e}")
            return False
    
    async def connect_nats(self) -> bool:
        """Connect to NATS server."""
        try:
            self.nats_client = NATS()
            await self.nats_client.connect(self.nats_url)
            self.nats_connected = True
            self.logger.info(f"✅ Connected to NATS server at {self.nats_url}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to NATS server: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from all services."""
        if self.grpc_channel:
            await self.grpc_channel.close()
            self.logger.info("Disconnected from gRPC")
        
        if self.nats_client and self.nats_connected:
            await self.nats_client.close()
            self.nats_connected = False
            self.logger.info("Disconnected from NATS")
    
    # gRPC Service Methods
    
    async def query_digital_twin(self, query_type: str, query_content: str, 
                                parameters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Query the Digital Twin."""
        if not self.grpc_stub:
            raise Exception("Not connected to gRPC server")
        
        request = digital_twin_pb2.QueryRequest(
            query_id=str(uuid.uuid4()),
            query_type=query_type,
            query_content=query_content,
            parameters=parameters or {},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        response = await self.grpc_stub.Query(request)
        
        return {
            "query_id": response.query_id,
            "success": response.success,
            "result": response.result,
            "confidence": response.confidence,
            "explanation": response.explanation,
            "timestamp": response.timestamp,
            "metadata": dict(response.metadata)
        }
    
    async def simulate_digital_twin(self, simulation_type: str, actions: List[Dict[str, Any]], 
                                   horizon_minutes: int = 60, 
                                   parameters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run simulation on Digital Twin."""
        if not self.grpc_stub:
            raise Exception("Not connected to gRPC server")
        
        # Convert actions to protobuf format
        pb_actions = []
        for action in actions:
            pb_action = digital_twin_pb2.ControlAction(
                action_id=action.get("action_id", str(uuid.uuid4())),
                action_type=action.get("action_type", ""),
                target=action.get("target", ""),
                params=action.get("params", {}),
                priority=action.get("priority", "normal"),
                timeout=action.get("timeout", 30.0)
            )
            pb_actions.append(pb_action)
        
        request = digital_twin_pb2.SimulationRequest(
            simulation_id=str(uuid.uuid4()),
            simulation_type=simulation_type,
            actions=pb_actions,
            horizon_minutes=horizon_minutes,
            parameters=parameters or {},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        response = await self.grpc_stub.Simulate(request)
        
        # Convert response to dict
        future_states = []
        for state in response.future_states:
            future_states.append({
                "timestamp": state.timestamp,
                "metrics": dict(state.metrics),
                "confidence": state.confidence,
                "description": state.description
            })
        
        return {
            "simulation_id": response.simulation_id,
            "success": response.success,
            "future_states": future_states,
            "confidence": response.confidence,
            "uncertainty_lower": response.uncertainty_lower,
            "uncertainty_upper": response.uncertainty_upper,
            "explanation": response.explanation,
            "timestamp": response.timestamp,
            "metadata": dict(response.metadata)
        }
    
    async def diagnose_digital_twin(self, anomaly_description: str, 
                                   context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Request diagnosis from Digital Twin."""
        if not self.grpc_stub:
            raise Exception("Not connected to gRPC server")
        
        request = digital_twin_pb2.DiagnosisRequest(
            diagnosis_id=str(uuid.uuid4()),
            anomaly_description=anomaly_description,
            context=context or {},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        response = await self.grpc_stub.Diagnose(request)
        
        # Convert hypotheses to dict
        hypotheses = []
        for hypothesis in response.hypotheses:
            hypotheses.append({
                "hypothesis": hypothesis.hypothesis,
                "probability": hypothesis.probability,
                "reasoning": hypothesis.reasoning,
                "evidence": list(hypothesis.evidence),
                "rank": hypothesis.rank
            })
        
        return {
            "diagnosis_id": response.diagnosis_id,
            "success": response.success,
            "hypotheses": hypotheses,
            "causal_chain": response.causal_chain,
            "confidence": response.confidence,
            "explanation": response.explanation,
            "supporting_evidence": list(response.supporting_evidence),
            "timestamp": response.timestamp,
            "metadata": dict(response.metadata)
        }
    
    async def manage_digital_twin(self, operation: str, 
                                 parameters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Send management request to Digital Twin."""
        if not self.grpc_stub:
            raise Exception("Not connected to gRPC server")
        
        request = digital_twin_pb2.ManagementRequest(
            request_id=str(uuid.uuid4()),
            operation=operation,
            parameters=parameters or {},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        response = await self.grpc_stub.Manage(request)
        
        # Convert health status if present
        health_status = None
        if response.health_status:
            health_status = {
                "status": response.health_status.status,
                "last_check": response.health_status.last_check,
                "performance_metrics": dict(response.health_status.performance_metrics),
                "issues": list(response.health_status.issues),
                "model_type": response.health_status.model_type,
                "model_version": response.health_status.model_version
            }
        
        return {
            "request_id": response.request_id,
            "success": response.success,
            "result": response.result,
            "metrics": dict(response.metrics),
            "health_status": health_status,
            "timestamp": response.timestamp
        }
    
    # NATS Methods
    
    async def publish_telemetry_event(self, name: str, value: Any, unit: str = "unknown", 
                                     source: str = "probe") -> bool:
        """Publish a telemetry event to NATS."""
        if not self.nats_connected:
            raise Exception("Not connected to NATS server")
        
        event = {
            "name": name,
            "value": value,
            "unit": unit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "tags": {"probe": "true"}
        }
        
        try:
            await self.nats_client.publish(
                "polaris.telemetry.events.stream",
                json.dumps(event).encode()
            )
            self.logger.info(f"Published telemetry event: {name} = {value} {unit}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to publish telemetry event: {e}")
            return False
    
    async def publish_telemetry_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Publish a batch of telemetry events to NATS."""
        if not self.nats_connected:
            raise Exception("Not connected to NATS server")
        
        batch = {
            "batch_id": str(uuid.uuid4()),
            "batch_timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(events),
            "events": events
        }
        
        try:
            await self.nats_client.publish(
                "polaris.telemetry.events.batch",
                json.dumps(batch).encode()
            )
            self.logger.info(f"Published telemetry batch with {len(events)} events")
            return True
        except Exception as e:
            self.logger.error(f"Failed to publish telemetry batch: {e}")
            return False
    
    async def publish_execution_result(self, action_id: str, action_type: str, 
                                      success: bool, message: str = "") -> bool:
        """Publish an execution result to NATS."""
        if not self.nats_connected:
            raise Exception("Not connected to NATS server")
        
        result = {
            "action_id": action_id,
            "action_type": action_type,
            "status": "success" if success else "failed",
            "success": success,
            "message": message,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_sec": 1.0,
            "metadata": {"probe": "true"}
        }
        
        try:
            await self.nats_client.publish(
                "polaris.execution.results",
                json.dumps(result).encode()
            )
            self.logger.info(f"Published execution result: {action_type} ({success})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to publish execution result: {e}")
            return False
    
    async def start_monitoring(self, subjects: List[str] = None):
        """Start monitoring NATS messages."""
        if not self.nats_connected:
            raise Exception("Not connected to NATS server")
        
        if subjects is None:
            subjects = [
                "polaris.telemetry.>",
                "polaris.execution.>",
                "polaris.digitaltwin.>"
            ]
        
        self.monitoring = True
        self.received_messages.clear()
        
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                message_info = {
                    "subject": msg.subject,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": data
                }
                self.received_messages.append(message_info)
                
                print(f"\n📨 Message on {msg.subject}:")
                print(f"   Data: {json.dumps(data, indent=2)[:200]}...")
                
            except Exception as e:
                print(f"Error processing message: {e}")
        
        # Subscribe to subjects
        for subject in subjects:
            await self.nats_client.subscribe(subject, cb=message_handler)
        
        self.logger.info(f"Started monitoring subjects: {subjects}")
    
    async def stop_monitoring(self):
        """Stop monitoring NATS messages."""
        self.monitoring = False
        # Note: NATS subscriptions will be cleaned up when connection closes
        self.logger.info("Stopped monitoring")


class DigitalTwinProbeShell(cmd.Cmd):
    """Interactive command shell for Digital Twin probe."""
    
    intro = """
🤖 Digital Twin Interactive Probe
=================================

Type 'help' or '?' to list commands.
Type 'help <command>' for detailed help on a command.
Type 'quit' or 'exit' to quit.

Available services:
- gRPC: Query, Simulate, Diagnose, Manage
- NATS: Publish events, Monitor messages
"""
    
    prompt = "dt-probe> "
    
    def __init__(self, probe: DigitalTwinProbe):
        super().__init__()
        self.probe = probe
        self.connected_grpc = False
        self.connected_nats = False
    
    def do_connect(self, args):
        """Connect to Digital Twin services.
        Usage: connect [grpc|nats|all]
        """
        service = args.strip().lower() or "all"
        
        if service in ["grpc", "all"]:
            try:
                success = self.probe.run_async(self.probe.connect_grpc())
                self.connected_grpc = success
            except Exception as e:
                print(f"❌ gRPC connection failed: {e}")
        
        if service in ["nats", "all"]:
            try:
                success = self.probe.run_async(self.probe.connect_nats())
                self.connected_nats = success
            except Exception as e:
                print(f"❌ NATS connection failed: {e}")
    
    def do_disconnect(self, args):
        """Disconnect from Digital Twin services."""
        try:
            self.probe.run_async(self.probe.disconnect())
            self.connected_grpc = False
            self.connected_nats = False
            print("✅ Disconnected from all services")
        except Exception as e:
            print(f"❌ Disconnect failed: {e}")
    
    def do_status(self, args):
        """Show connection status."""
        print(f"gRPC: {'✅ Connected' if self.connected_grpc else '❌ Disconnected'}")
        print(f"NATS: {'✅ Connected' if self.connected_nats else '❌ Disconnected'}")
        print(f"gRPC endpoint: {self.probe.grpc_host}:{self.probe.grpc_port}")
        print(f"NATS endpoint: {self.probe.nats_url}")
    
    # gRPC Commands
    
    def do_query(self, args):
        """Query the Digital Twin.
        Usage: query <type> <content>
        Types: current_state, historical, natural_language
        Example: query current_state "What is the CPU usage?"
        """
        parts = args.split(None, 1)
        if len(parts) < 2:
            print("Usage: query <type> <content>")
            return
        
        query_type, query_content = parts
        
        try:
            result = self.probe.run_async(
                self.probe.query_digital_twin(query_type, query_content)
            )
            print(f"✅ Query Result:")
            print(f"   Success: {result['success']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Result: {result['result']}")
            print(f"   Explanation: {result['explanation']}")
        except Exception as e:
            print(f"❌ Query failed: {e}")
    
    def do_simulate(self, args):
        """Run simulation on Digital Twin.
        Usage: simulate <type> <horizon_minutes> [action_type:target:params]
        Types: forecast, what_if, scenario
        Example: simulate what_if 60 ADD_SERVER:web_cluster:count=2
        """
        parts = args.split()
        if len(parts) < 2:
            print("Usage: simulate <type> <horizon_minutes> [action_type:target:params]")
            return
        
        sim_type = parts[0]
        horizon = int(parts[1])
        
        # Parse actions
        actions = []
        for action_str in parts[2:]:
            action_parts = action_str.split(":")
            if len(action_parts) >= 2:
                action = {
                    "action_type": action_parts[0],
                    "target": action_parts[1],
                    "params": {}
                }
                if len(action_parts) > 2:
                    # Parse params (key=value,key=value)
                    for param in action_parts[2].split(","):
                        if "=" in param:
                            key, value = param.split("=", 1)
                            action["params"][key] = value
                actions.append(action)
        
        try:
            result = self.probe.run_async(
                self.probe.simulate_digital_twin(sim_type, actions, horizon)
            )
            print(f"✅ Simulation Result:")
            print(f"   Success: {result['success']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Future States: {len(result['future_states'])}")
            print(f"   Explanation: {result['explanation']}")
            
            for i, state in enumerate(result['future_states'][:3]):  # Show first 3
                print(f"   State {i+1}: {state['description']} (confidence: {state['confidence']})")
                
        except Exception as e:
            print(f"❌ Simulation failed: {e}")
    
    def do_diagnose(self, args):
        """Request diagnosis from Digital Twin.
        Usage: diagnose <anomaly_description>
        Example: diagnose "High CPU usage detected"
        """
        if not args.strip():
            print("Usage: diagnose <anomaly_description>")
            return
        
        try:
            result = self.probe.run_async(
                self.probe.diagnose_digital_twin(args.strip())
            )
            print(f"✅ Diagnosis Result:")
            print(f"   Success: {result['success']}")
            print(f"   Confidence: {result['confidence']}")
            print(f"   Hypotheses: {len(result['hypotheses'])}")
            print(f"   Explanation: {result['explanation']}")
            
            for i, hypothesis in enumerate(result['hypotheses'][:3]):  # Show first 3
                print(f"   {i+1}. {hypothesis['hypothesis']} (prob: {hypothesis['probability']:.2f})")
                
        except Exception as e:
            print(f"❌ Diagnosis failed: {e}")
    
    def do_manage(self, args):
        """Send management request to Digital Twin.
        Usage: manage <operation>
        Operations: health_check, reload_model, get_metrics, reset_state
        Example: manage health_check
        """
        if not args.strip():
            print("Usage: manage <operation>")
            return
        
        try:
            result = self.probe.run_async(
                self.probe.manage_digital_twin(args.strip())
            )
            print(f"✅ Management Result:")
            print(f"   Success: {result['success']}")
            print(f"   Result: {result['result']}")
            
            if result['health_status']:
                health = result['health_status']
                print(f"   Health Status: {health['status']}")
                print(f"   Model Type: {health['model_type']}")
                if health['issues']:
                    print(f"   Issues: {health['issues']}")
                    
        except Exception as e:
            print(f"❌ Management request failed: {e}")
    
    # NATS Commands
    
    def do_publish_telemetry(self, args):
        """Publish telemetry event to NATS.
        Usage: publish_telemetry <name> <value> [unit]
        Example: publish_telemetry cpu.usage 85.5 percent
        """
        parts = args.split()
        if len(parts) < 2:
            print("Usage: publish_telemetry <name> <value> [unit]")
            return
        
        name = parts[0]
        try:
            value = float(parts[1])
        except ValueError:
            value = parts[1]  # Keep as string
        
        unit = parts[2] if len(parts) > 2 else "unknown"
        
        try:
            success = self.probe.run_async(
                self.probe.publish_telemetry_event(name, value, unit)
            )
            if success:
                print(f"✅ Published telemetry: {name} = {value} {unit}")
        except Exception as e:
            print(f"❌ Publish failed: {e}")
    
    def do_publish_execution(self, args):
        """Publish execution result to NATS.
        Usage: publish_execution <action_type> <success> [message]
        Example: publish_execution ADD_SERVER true "Server added successfully"
        """
        parts = args.split(None, 2)
        if len(parts) < 2:
            print("Usage: publish_execution <action_type> <success> [message]")
            return
        
        action_type = parts[0]
        success = parts[1].lower() in ["true", "1", "yes"]
        message = parts[2] if len(parts) > 2 else ""
        
        try:
            result = self.probe.run_async(
                self.probe.publish_execution_result(
                    str(uuid.uuid4()), action_type, success, message
                )
            )
            if result:
                print(f"✅ Published execution result: {action_type} ({success})")
        except Exception as e:
            print(f"❌ Publish failed: {e}")
    
    def do_monitor(self, args):
        """Start/stop monitoring NATS messages.
        Usage: monitor [start|stop] [subjects...]
        Example: monitor start polaris.telemetry.> polaris.execution.>
        """
        parts = args.split()
        if not parts:
            print("Usage: monitor [start|stop] [subjects...]")
            return
        
        command = parts[0].lower()
        
        if command == "start":
            subjects = parts[1:] if len(parts) > 1 else None
            try:
                self.probe.run_async(self.probe.start_monitoring(subjects))
                print("✅ Started monitoring")
            except Exception as e:
                print(f"❌ Monitor start failed: {e}")
                
        elif command == "stop":
            try:
                self.probe.run_async(self.probe.stop_monitoring())
                print("✅ Stopped monitoring")
            except Exception as e:
                print(f"❌ Monitor stop failed: {e}")
        else:
            print("Usage: monitor [start|stop]")
    
    def do_messages(self, args):
        """Show received messages.
        Usage: messages [count]
        Example: messages 10
        """
        count = 10
        if args.strip():
            try:
                count = int(args.strip())
            except ValueError:
                print("Invalid count")
                return
        
        messages = self.probe.received_messages[-count:]
        print(f"📨 Last {len(messages)} messages:")
        
        for i, msg in enumerate(messages):
            print(f"{i+1}. [{msg['timestamp']}] {msg['subject']}")
            print(f"   {json.dumps(msg['data'], indent=2)[:100]}...")
    
    # Utility Commands
    
    def do_test(self, args):
        """Run a quick test of all Digital Twin services.
        Usage: test
        """
        print("🧪 Running Digital Twin test suite...")
        
        # Test gRPC services
        if self.connected_grpc:
            print("\n1. Testing Query service...")
            self.do_query("current_state What is the system status?")
            
            print("\n2. Testing Management service...")
            self.do_manage("health_check")
            
            print("\n3. Testing Simulation service...")
            self.do_simulate("what_if 30 ADD_SERVER:test_cluster:count=1")
            
            print("\n4. Testing Diagnosis service...")
            self.do_diagnose("Test anomaly for probe testing")
        else:
            print("❌ gRPC not connected - skipping gRPC tests")
        
        # Test NATS publishing
        if self.connected_nats:
            print("\n5. Testing NATS telemetry publishing...")
            self.do_publish_telemetry("test.probe.metric 42.0 units")
            
            print("\n6. Testing NATS execution publishing...")
            self.do_publish_execution("TEST_ACTION true Probe test completed")
        else:
            print("❌ NATS not connected - skipping NATS tests")
        
        print("\n✅ Test suite completed")
    
    def do_quit(self, args):
        """Quit the probe."""
        print("Disconnecting and exiting...")
        self.do_disconnect("")
        return True
    
    def do_exit(self, args):
        """Exit the probe."""
        return self.do_quit(args)
    
    def do_EOF(self, args):
        """Handle Ctrl+D."""
        print()
        return self.do_quit(args)


def print_detailed_help():
    """Print detailed usage help."""
    help_text = """
🤖 POLARIS Digital Twin Interactive Probe
=========================================

DESCRIPTION:
    Interactive command-line tool for probing, monitoring, and debugging the 
    Digital Twin component. Provides full access to gRPC services and NATS 
    messaging for testing and observability.

USAGE:
    python digital_twin_probe.py [OPTIONS]

OPTIONS:
    --grpc-host HOST        gRPC server hostname (default: localhost)
    --grpc-port PORT        gRPC server port (default: 50051)
    --nats-url URL          NATS server URL (default: nats://localhost:4222)
    --help, -h              Show this help message

REQUIREMENTS:
    pip install grpcio grpcio-tools nats-py

QUICK START:
    1. Start Digital Twin component:
       python src/scripts/start_digital_twin.py

    2. Start the probe:
       python scripts/digital_twin_probe.py

    3. Connect to services:
       dt-probe> connect all

    4. Run a test:
       dt-probe> test

INTERACTIVE COMMANDS:

📡 Connection Management:
    connect [grpc|nats|all]     Connect to Digital Twin services
    disconnect                  Disconnect from all services
    status                      Show connection status

🔍 gRPC Services (Digital Twin API):
    query <type> <content>      Query the Digital Twin
        Types: current_state, historical, natural_language
        Example: query current_state "What is the CPU usage?"

    simulate <type> <horizon> [actions]  Run predictive simulations
        Types: forecast, what_if, scenario
        Horizon: minutes into the future
        Actions: action_type:target:params (comma-separated params)
        Example: simulate what_if 60 ADD_SERVER:web_cluster:count=2,priority=high

    diagnose <description>      Request root cause analysis
        Example: diagnose "High response times detected"

    manage <operation>          Digital Twin management
        Operations: health_check, reload_model, get_metrics, reset_state
        Example: manage health_check

📨 NATS Operations (Event Publishing):
    publish_telemetry <name> <value> [unit]  Publish telemetry event
        Example: publish_telemetry cpu.usage 85.5 percent

    publish_execution <type> <success> [message]  Publish execution result
        Example: publish_execution ADD_SERVER true "Server added successfully"

    monitor start [subjects...]  Start monitoring NATS messages
        Example: monitor start polaris.telemetry.> polaris.execution.>

    monitor stop                Stop monitoring messages

    messages [count]            Show last N received messages
        Example: messages 10

🛠️ Utilities:
    test                        Run comprehensive test suite
    help [command]              Show help for specific command
    quit, exit, Ctrl+D         Exit the probe

EXAMPLE SESSION:
    $ python scripts/digital_twin_probe.py
    dt-probe> connect all
    ✅ Connected to gRPC server at localhost:50051
    ✅ Connected to NATS server at nats://localhost:4222

    dt-probe> status
    gRPC: ✅ Connected
    NATS: ✅ Connected

    dt-probe> query current_state "What is the system status?"
    ✅ Query Result:
       Success: True
       Confidence: 0.85
       Result: System is operating normally...

    dt-probe> simulate what_if 30 ADD_SERVER:web_cluster:count=2
    ✅ Simulation Result:
       Success: True
       Confidence: 0.92
       Future States: 3
       Explanation: Adding 2 servers will improve response times...

    dt-probe> publish_telemetry cpu.usage 75.5 percent
    ✅ Published telemetry: cpu.usage = 75.5 percent

    dt-probe> monitor start
    ✅ Started monitoring
    📨 Message on polaris.telemetry.events.stream:
       Data: {"name": "cpu.usage", "value": 75.5, "unit": "percent"}...

    dt-probe> test
    🧪 Running Digital Twin test suite...
    [Runs comprehensive tests of all services]

    dt-probe> quit
    Disconnecting and exiting...

TROUBLESHOOTING:
    Connection Issues:
    - Ensure Digital Twin is running: python src/scripts/start_digital_twin.py
    - Check gRPC port: netstat -an | grep 50051
    - Check NATS server: nats-server or ./bin/nats-server

    gRPC Errors:
    - Verify protobuf files are generated: python scripts/generate_proto.py
    - Check Digital Twin health: dt-probe> manage health_check

    NATS Errors:
    - Verify NATS server is running
    - Check NATS URL configuration
    - Test with: nats sub "polaris.>"

INTEGRATION WITH POLARIS:
    The probe can interact with the Digital Twin exactly as other POLARIS 
    components would:
    
    - Monitor adapters publish telemetry → Digital Twin processes automatically
    - Execution adapters publish results → Digital Twin tracks system changes
    - External clients query via gRPC → Get intelligent system insights
    - Probe publishes test events → Verify Digital Twin integration

    This makes it perfect for:
    - Testing Digital Twin functionality
    - Debugging integration issues
    - Monitoring system behavior
    - Validating AI/ML model responses

ADVANCED USAGE:
    Custom gRPC endpoint:
        python digital_twin_probe.py --grpc-host remote-host --grpc-port 50052

    Custom NATS server:
        python digital_twin_probe.py --nats-url nats://remote-nats:4222

    Monitor specific subjects:
        dt-probe> monitor start polaris.telemetry.events.batch polaris.execution.results

    Batch telemetry publishing:
        dt-probe> publish_telemetry cpu.usage 75.5 percent
        dt-probe> publish_telemetry memory.usage 60.2 percent
        dt-probe> publish_telemetry disk.usage 45.8 percent

For more information, see:
- docs/README_DIGITAL_TWIN.md
- docs/digital_twin_integration.md
"""
    print(help_text)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Digital Twin Interactive Probe - Interactive tool for testing and debugging the Digital Twin component",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Start with default settings
  %(prog)s --grpc-host remote --grpc-port 50052  # Connect to remote gRPC
  %(prog)s --nats-url nats://remote:4222      # Connect to remote NATS
  %(prog)s --help                             # Show detailed help

For detailed usage information, run with --help flag.
        """,
        add_help=False  # We'll handle help manually
    )
    
    parser.add_argument(
        "--grpc-host",
        default="localhost",
        help="gRPC server host (default: localhost)"
    )
    
    parser.add_argument(
        "--grpc-port",
        type=int,
        default=50051,
        help="gRPC server port (default: 50051)"
    )
    
    parser.add_argument(
        "--nats-url",
        default="nats://localhost:4222",
        help="NATS server URL (default: nats://localhost:4222)"
    )
    
    parser.add_argument(
        "--help", "-h",
        action="store_true",
        help="Show detailed help and usage information"
    )
    
    args = parser.parse_args()
    
    # Handle help flag
    if args.help:
        print_detailed_help()
        return
    
    # Create probe
    probe = DigitalTwinProbe(
        grpc_host=args.grpc_host,
        grpc_port=args.grpc_port,
        nats_url=args.nats_url
    )
    
    # Start event loop
    probe.start_event_loop()
    
    # Create and run shell
    shell = DigitalTwinProbeShell(probe)
    
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Cleanup
        try:
            probe.run_async(probe.disconnect())
        except:
            pass
        
        if probe.loop:
            probe.loop.call_soon_threadsafe(probe.loop.stop)


if __name__ == "__main__":
    main()