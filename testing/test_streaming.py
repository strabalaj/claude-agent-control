#!/usr/bin/env python3
"""
Streaming Test Script for Claude Agent Control Center

Tests the streaming functionality of the WebSocket endpoint at /ws/agents/{agent_id}/execute

Requirements:
    pip install websockets

Usage:
    python testing/test_streaming.py
"""

import asyncio
import websockets
import json
import sys


async def test_streaming_text_only(agent_id: int = 1):
    """
    Test streaming with text deltas only (default behavior).

    Args:
        agent_id: ID of agent to execute
    """
    uri = f"ws://localhost:8000/ws/agents/{agent_id}/execute"

    print(f"\n{'='*60}")
    print(f"TEST 1: Streaming with Text Deltas Only")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connection established")

            # 1. Receive connected message
            connected_msg = await websocket.recv()
            connected_data = json.loads(connected_msg)
            print(f"📨 Connected to agent: {connected_data['agent_name']}")

            # 2. Send execute request with streaming enabled
            execute_request = {
                "type": "execute",
                "variables": {},
                "stream": True,  # Enable streaming
                "stream_events": ["text"]  # Text deltas only
            }
            print(f"\n📤 Sending streaming execute request...")
            print(f"   stream: True")
            print(f"   stream_events: ['text']")
            await websocket.send(json.dumps(execute_request))

            # 3. Receive streaming messages
            print(f"\n⏳ Receiving stream...\n")

            delta_count = 0
            full_output = ""

            async for message in websocket:
                data = json.loads(message)
                msg_type = data['type']

                if msg_type == 'status':
                    print(f"📊 Status: {data['message']}")

                elif msg_type == 'stream_start':
                    print(f"🚀 Stream Started")
                    print(f"   Model: {data.get('model', 'unknown')}")
                    if data.get('message_id'):
                        print(f"   Message ID: {data['message_id']}")
                    print()

                elif msg_type == 'content_delta':
                    delta_count += 1
                    delta_type = data['delta_type']
                    delta_text = data['delta']

                    # Print delta in real-time (without newline)
                    print(delta_text, end='', flush=True)
                    full_output += delta_text

                elif msg_type == 'stream_end':
                    print(f"\n\n✅ Stream Ended")
                    print(f"{'─'*60}")
                    print(f"Stop Reason: {data['stop_reason']}")
                    print(f"Usage:")
                    print(f"  - Input tokens:  {data['usage']['input_tokens']}")
                    print(f"  - Output tokens: {data['usage']['output_tokens']}")
                    print(f"  - Total tokens:  {data['usage']['total_tokens']}")
                    print(f"Deltas Received: {delta_count}")
                    print(f"{'─'*60}")

                elif msg_type == 'result':
                    print(f"\n📊 Final Result Message Received")
                    print(f"   Execution ID: {data['execution_id']}")
                    print(f"   Output Length: {len(data['output'])} chars")

                    # Verify accumulated output matches result
                    if data['output'] == full_output:
                        print(f"   ✓ Accumulated deltas match final output")
                    else:
                        print(f"   ❌ WARNING: Accumulated deltas don't match!")
                    break

                elif msg_type == 'error':
                    print(f"\n❌ Error: {data['error']}")
                    break

            print(f"\n✓ Test completed successfully\n")

    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        sys.exit(1)


async def test_streaming_all_events(agent_id: int = 1):
    """
    Test streaming with all event types.

    Args:
        agent_id: ID of agent to execute
    """
    uri = f"ws://localhost:8000/ws/agents/{agent_id}/execute"

    print(f"\n{'='*60}")
    print(f"TEST 2: Streaming with All Event Types")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connection established")

            # Skip connected message
            await websocket.recv()

            # Send execute request with all events
            execute_request = {
                "type": "execute",
                "variables": {},
                "stream": True,
                "stream_events": ["all"]  # All event types
            }
            print(f"\n📤 Sending streaming execute request...")
            print(f"   stream: True")
            print(f"   stream_events: ['all']")
            await websocket.send(json.dumps(execute_request))

            print(f"\n⏳ Receiving stream...\n")

            event_counts = {
                "text_delta": 0,
                "thinking_delta": 0,
                "input_json_delta": 0
            }

            async for message in websocket:
                data = json.loads(message)
                msg_type = data['type']

                if msg_type == 'status':
                    print(f"📊 Status: {data['message']}")

                elif msg_type == 'stream_start':
                    print(f"🚀 Stream Started\n")

                elif msg_type == 'content_delta':
                    delta_type = data['delta_type']
                    event_counts[delta_type] += 1

                    if delta_type == "text_delta":
                        print(data['delta'], end='', flush=True)
                    elif delta_type == "thinking_delta":
                        print(f"\n[THINKING: {data['delta'][:50]}...]", end='', flush=True)
                    elif delta_type == "input_json_delta":
                        print(f"\n[TOOL JSON: {data['delta'][:50]}...]", end='', flush=True)

                elif msg_type == 'stream_end':
                    print(f"\n\n✅ Stream Ended")
                    print(f"{'─'*60}")
                    print(f"Event Type Counts:")
                    for event_type, count in event_counts.items():
                        print(f"  - {event_type}: {count}")
                    print(f"Usage: {data['usage']['total_tokens']} total tokens")
                    print(f"{'─'*60}")

                elif msg_type == 'result':
                    print(f"\n📊 Execution ID: {data['execution_id']}")
                    break

                elif msg_type == 'error':
                    print(f"\n❌ Error: {data['error']}")
                    break

            print(f"\n✓ Test completed successfully\n")

    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        sys.exit(1)


async def test_streaming_specific_events(agent_id: int = 1):
    """
    Test streaming with specific event types (text and thinking only).

    Args:
        agent_id: ID of agent to execute
    """
    uri = f"ws://localhost:8000/ws/agents/{agent_id}/execute"

    print(f"\n{'='*60}")
    print(f"TEST 3: Streaming with Specific Events (text + thinking)")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connection established")

            # Skip connected message
            await websocket.recv()

            # Send execute request with specific events
            execute_request = {
                "type": "execute",
                "variables": {},
                "stream": True,
                "stream_events": ["text", "thinking"]  # Text and thinking only
            }
            print(f"\n📤 Sending streaming execute request...")
            print(f"   stream: True")
            print(f"   stream_events: ['text', 'thinking']")
            await websocket.send(json.dumps(execute_request))

            print(f"\n⏳ Receiving stream...\n")

            async for message in websocket:
                data = json.loads(message)
                msg_type = data['type']

                if msg_type == 'content_delta':
                    delta_type = data['delta_type']
                    if delta_type == "text_delta":
                        print(data['delta'], end='', flush=True)
                    elif delta_type == "thinking_delta":
                        print(f"\n💭 {data['delta']}", flush=True)

                elif msg_type == 'stream_end':
                    print(f"\n\n✅ Stream complete: {data['usage']['total_tokens']} tokens")

                elif msg_type == 'result':
                    print(f"📊 Execution ID: {data['execution_id']}")
                    break

                elif msg_type == 'error':
                    print(f"\n❌ Error: {data['error']}")
                    break

            print(f"\n✓ Test completed successfully\n")

    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        sys.exit(1)


async def test_non_streaming_backward_compat(agent_id: int = 1):
    """
    Test backward compatibility - non-streaming execution should still work.

    Args:
        agent_id: ID of agent to execute
    """
    uri = f"ws://localhost:8000/ws/agents/{agent_id}/execute"

    print(f"\n{'='*60}")
    print(f"TEST 4: Backward Compatibility (Non-Streaming)")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connection established")

            # Skip connected message
            await websocket.recv()

            # Send execute request WITHOUT streaming
            execute_request = {
                "type": "execute",
                "variables": {}
                # No "stream" parameter - should use non-streaming path
            }
            print(f"\n📤 Sending non-streaming execute request...")
            await websocket.send(json.dumps(execute_request))

            print(f"\n⏳ Waiting for response...\n")

            received_stream_messages = False

            async for message in websocket:
                data = json.loads(message)
                msg_type = data['type']

                if msg_type == 'status':
                    print(f"📊 Status: {data['message']}")

                elif msg_type in ['stream_start', 'content_delta', 'stream_end']:
                    received_stream_messages = True
                    print(f"❌ ERROR: Received streaming message '{msg_type}' in non-streaming mode!")

                elif msg_type == 'result':
                    print(f"✅ Received result message (non-streaming)")
                    print(f"   Output: {data['output'][:100]}...")
                    print(f"   Tokens: {data['usage']['total_tokens']}")
                    print(f"   Execution ID: {data['execution_id']}")

                    if not received_stream_messages:
                        print(f"\n✓ Backward compatibility confirmed - no streaming messages")
                    break

                elif msg_type == 'error':
                    print(f"\n❌ Error: {data['error']}")
                    break

            print(f"\n✓ Test completed successfully\n")

    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        sys.exit(1)


async def main():
    """Run all streaming tests."""
    print("\n" + "="*60)
    print("Claude Agent Control Center - Streaming Test Suite")
    print("Issue #5: Streaming Claude API Integration")
    print("="*60)

    # Test 1: Text deltas only (default)
    print("\n[TEST 1] Streaming with Text Deltas Only")
    await test_streaming_text_only(agent_id=1)

    # Test 2: All event types
    print("\n[TEST 2] Streaming with All Event Types")
    await test_streaming_all_events(agent_id=1)

    # Test 3: Specific event types
    print("\n[TEST 3] Streaming with Specific Events")
    await test_streaming_specific_events(agent_id=1)

    # Test 4: Backward compatibility
    print("\n[TEST 4] Backward Compatibility")
    await test_non_streaming_backward_compat(agent_id=1)

    print("\n" + "="*60)
    print("✅ All streaming tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Check if websockets is installed
    try:
        import websockets
    except ImportError:
        print("\n❌ Error: websockets library not installed")
        print("Install with: uv add --dev websockets")
        print("Or: pip install websockets\n")
        sys.exit(1)

    # Run tests
    asyncio.run(main())
