#!/usr/bin/env python3
"""
NATS Spy - Real-time NATS message visibility tool for POLARIS.

This tool connects to the NATS server and subscribes to POLARIS subjects,
displaying messages in real-time with color coding for easy debugging.
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, Any

from nats.aio.client import Client as NATS
from nats.aio.msg import Msg


class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Subject colors
    TELEMETRY = "\033[36m"      # Cyan
    EXECUTION = "\033[33m"      # Yellow
    RESULTS = "\033[32m"        # Green
    METRICS = "\033[35m"        # Magenta
    ERROR = "\033[31m"          # Red
    
    # Component colors
    TIMESTAMP = "\033[90m"      # Gray
    SUBJECT = "\033[94m"        # Light Blue
    SIZE = "\033[37m"           # White
    
    # Data colors
    SUCCESS = "\033[92m"        # Light Green
    FAILURE = "\033[91m"        # Light Red
    VALUE = "\033[93m"          # Light Yellow


class NATSSpy:
    """NATS message spy for monitoring POLARIS message bus."""
    
    def __init__(self, nats_url: str, subjects: list, show_data: bool = False):
        """Initialize the NATS spy.
        
        Args:
            nats_url: NATS server URL
            subjects: List of subjects to monitor
            show_data: Whether to show message data content
        """
        self.nats_url = nats_url
        self.subjects = subjects
        self.show_data = show_data
        self.nc: NATS = None
        self.running = False
        self.message_count = 0
        
        # Setup logging
        logging.basicConfig(level=logging.WARNING)
        self.logger = logging.getLogger(__name__)
    
    def _get_subject_color(self, subject: str) -> str:
        """Get color for subject based on type."""
        if "telemetry" in subject:
            return Colors.TELEMETRY
        elif "execution" in subject and "results" in subject:
            return Colors.RESULTS
        elif "execution" in subject:
            return Colors.EXECUTION
        elif "metrics" in subject:
            return Colors.METRICS
        else:
            return Colors.SUBJECT
    
    def _format_timestamp(self) -> str:
        """Format current timestamp."""
        now = datetime.now()
        return f"{Colors.TIMESTAMP}{now.strftime('%H:%M:%S.%f')[:-3]}{Colors.RESET}"
    
    def _format_size(self, size: int) -> str:
        """Format message size."""
        if size < 1024:
            return f"{Colors.SIZE}{size}B{Colors.RESET}"
        elif size < 1024 * 1024:
            return f"{Colors.SIZE}{size/1024:.1f}KB{Colors.RESET}"
        else:
            return f"{Colors.SIZE}{size/(1024*1024):.1f}MB{Colors.RESET}"
    
    def _format_json_preview(self, data: Dict[str, Any], max_length: int = 100) -> str:
        """Format JSON data for preview."""
        try:
            # Extract key fields for preview
            preview_parts = []
            
            # Common fields to highlight
            if "action_type" in data:
                preview_parts.append(f"type={Colors.VALUE}{data['action_type']}{Colors.RESET}")
            
            if "name" in data:
                preview_parts.append(f"name={Colors.VALUE}{data['name']}{Colors.RESET}")
            
            if "success" in data:
                color = Colors.SUCCESS if data["success"] else Colors.FAILURE
                preview_parts.append(f"success={color}{data['success']}{Colors.RESET}")
            
            if "value" in data:
                preview_parts.append(f"value={Colors.VALUE}{data['value']}{Colors.RESET}")
            
            if "metric" in data:
                preview_parts.append(f"metric={Colors.VALUE}{data['metric']}{Colors.RESET}")
            
            if "count" in data:
                preview_parts.append(f"count={Colors.VALUE}{data['count']}{Colors.RESET}")
            
            preview = " ".join(preview_parts)
            
            if len(preview) > max_length:
                preview = preview[:max_length-3] + "..."
            
            return preview if preview else f"{Colors.DIM}(no preview){Colors.RESET}"
            
        except Exception:
            return f"{Colors.DIM}(preview error){Colors.RESET}"
    
    def _print_message(self, subject: str, data: bytes, reply: str = None):
        """Print formatted message."""
        self.message_count += 1
        
        # Format components
        timestamp = self._format_timestamp()
        subject_color = self._get_subject_color(subject)
        subject_formatted = f"{subject_color}{subject}{Colors.RESET}"
        size_formatted = self._format_size(len(data))
        
        # Try to parse JSON for preview
        preview = ""
        json_data = None
        
        try:
            json_data = json.loads(data.decode())
            if not self.show_data:
                preview = f" | {self._format_json_preview(json_data)}"
        except Exception:
            if not self.show_data:
                preview = f" | {Colors.DIM}(binary data){Colors.RESET}"
        
        # Print header
        reply_info = f" | reply={reply}" if reply else ""
        print(f"{timestamp} | {subject_formatted} | {size_formatted}{reply_info}{preview}")
        
        # Print data if requested
        if self.show_data and json_data:
            try:
                formatted_json = json.dumps(json_data, indent=2)
                # Add indentation and dim color
                indented = "\n".join(f"  {Colors.DIM}{line}{Colors.RESET}" for line in formatted_json.split("\n"))
                print(indented)
            except Exception:
                print(f"  {Colors.DIM}{data.decode()[:500]}{Colors.RESET}")
        elif self.show_data:
            # Show raw data
            print(f"  {Colors.DIM}{data.decode()[:500]}{Colors.RESET}")
        
        print()  # Empty line for readability
    
    async def _message_handler(self, msg: Msg):
        """Handle incoming NATS messages."""
        try:
            self._print_message(msg.subject, msg.data, msg.reply)
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
    
    async def start(self):
        """Start the NATS spy."""
        print(f"{Colors.BOLD}🕵️  POLARIS NATS Spy{Colors.RESET}")
        print(f"Connecting to: {Colors.SUBJECT}{self.nats_url}{Colors.RESET}")
        print(f"Monitoring subjects: {', '.join(f'{Colors.SUBJECT}{s}{Colors.RESET}' for s in self.subjects)}")
        print(f"Show data: {Colors.VALUE}{self.show_data}{Colors.RESET}")
        print("-" * 80)
        
        try:
            # Connect to NATS
            self.nc = NATS()
            await self.nc.connect(self.nats_url)
            
            print(f"{Colors.SUCCESS}✅ Connected to NATS{Colors.RESET}")
            
            # Subscribe to subjects
            for subject in self.subjects:
                await self.nc.subscribe(subject, cb=self._message_handler)
                print(f"{Colors.SUCCESS}📡 Subscribed to {subject}{Colors.RESET}")
            
            print("-" * 80)
            self.running = True
            
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"{Colors.ERROR}❌ Error: {e}{Colors.RESET}")
            raise
    
    async def stop(self):
        """Stop the NATS spy."""
        self.running = False
        if self.nc:
            await self.nc.close()
        
        print(f"\n{Colors.DIM}📊 Total messages received: {self.message_count}{Colors.RESET}")
        print(f"{Colors.SUCCESS}👋 NATS Spy stopped{Colors.RESET}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NATS Spy - Monitor POLARIS message bus in real-time"
    )
    
    parser.add_argument(
        "--nats-url",
        default="nats://localhost:4222",
        help="NATS server URL (default: nats://localhost:4222)"
    )
    
    parser.add_argument(
        "--subjects",
        nargs="+",
        default=["polaris.>"],
        help="Subjects to monitor (default: polaris.>)"
    )
    
    parser.add_argument(
        "--show-data",
        action="store_true",
        help="Show full message data content"
    )
    
    parser.add_argument(
        "--preset",
        choices=["all", "telemetry", "execution", "results"],
        help="Use predefined subject sets"
    )
    
    args = parser.parse_args()
    
    # Handle presets
    if args.preset == "all":
        subjects = ["polaris.>"]
    elif args.preset == "telemetry":
        subjects = ["polaris.telemetry.>"]
    elif args.preset == "execution":
        subjects = ["polaris.execution.actions", "polaris.execution.metrics"]
    elif args.preset == "results":
        subjects = ["polaris.execution.results"]
    else:
        subjects = args.subjects
    
    # Create and start spy
    spy = NATSSpy(
        nats_url=args.nats_url,
        subjects=subjects,
        show_data=args.show_data
    )
    
    # Setup signal handling
    stop_event = asyncio.Event()
    
    def signal_handler():
        print(f"\n{Colors.DIM}🛑 Received shutdown signal{Colors.RESET}")
        stop_event.set()
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda *_: signal_handler())
    
    # Start spy and wait for stop signal
    try:
        spy_task = asyncio.create_task(spy.start())
        stop_task = asyncio.create_task(stop_event.wait())
        
        # Wait for either spy to finish or stop signal
        done, pending = await asyncio.wait(
            [spy_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
        
        # Stop spy
        await spy.stop()
        
    except KeyboardInterrupt:
        await spy.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass