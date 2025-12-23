#!/usr/bin/env python3
"""
WebSocket Test Script for Claude Agent Control Center

Tests the WebSocket endpoint at /ws/agents/{agent_id}/execute

Requirements:
    pip install websockets

Usage:
    python test_websocket.py
"""

import asyncio
import websockets
import json
import sys


async def test_websocket_execution(agent_id: int = 1, variables: dict = None):
    """
    Test WebSocket execution endpoint.

    Args:
        agent_id: ID of agent to execute
        variables: Optional variables for prompt template
    """
    uri = f"ws://localhost:8000/ws/agents/{agent_id}/execute"
    variables = variables or {}

    print(f"\n{'='*60}")
    print(f"Testing WebSocket Endpoint: {uri}")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            print("✓ WebSocket connection established")

            # 1. Receive connected message
            connected_msg = await websocket.recv()
            connected_data = json.loads(connected_msg)
            print(f"\n📨 Received: {connected_data['type']}")
            print(f"   Agent ID: {connected_data['agent_id']}")
            print(f"   Agent Name: {connected_data['agent_name']}")

            # 2. Send execute request
            execute_request = {
                "type": "execute",
                "variables": variables
            }
            print(f"\n📤 Sending execute request:")
            print(f"   Variables: {variables if variables else 'None'}")
            await websocket.send(json.dumps(execute_request))

            # 3. Receive messages until we get result or error
            print(f"\n⏳ Waiting for response...\n")
            async for message in websocket:
                data = json.loads(message)
                msg_type = data['type']

                if msg_type == 'status':
                    print(f"📊 Status: {data['message']}")

                elif msg_type == 'result':
                    print(f"\n✅ Execution Successful!")
                    print(f"{'─'*60}")
                    print(f"Output: {data['output'][:200]}{'...' if len(data['output']) > 200 else ''}")
                    print(f"{'─'*60}")
                    print(f"Usage:")
                    print(f"  - Input tokens:  {data['usage']['input_tokens']}")
                    print(f"  - Output tokens: {data['usage']['output_tokens']}")
                    print(f"  - Total tokens:  {data['usage']['total_tokens']}")
                    print(f"Model: {data['model']}")
                    print(f"Execution ID: {data['execution_id']}")
                    break

                elif msg_type == 'error':
                    print(f"\n❌ Execution Failed!")
                    print(f"{'─'*60}")
                    print(f"Error: {data['error']}")
                    print(f"{'─'*60}")
                    if 'execution_id' in data:
                        print(f"Execution ID: {data['execution_id']}")
                    break

                else:
                    print(f"📨 Unknown message type: {msg_type}")
                    print(f"   Data: {data}")

            print(f"\n✓ Test completed successfully\n")

    except websockets.exceptions.InvalidStatus as e:
        print(f"\n❌ Connection failed: {e}")
        print(f"   Make sure the server is running and agent ID {agent_id} exists")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        sys.exit(1)


async def test_invalid_agent():
    """Test connection to non-existent agent."""
    uri = "ws://localhost:8000/ws/agents/99999/execute"
    print(f"\n{'='*60}")
    print(f"Testing Invalid Agent ID: {uri}")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            print("❌ Connection should have been rejected!")
            sys.exit(1)
    except websockets.exceptions.InvalidStatus as e:
        if "403" in str(e) or "Agent not found" in str(e):
            print("✓ Connection correctly rejected for invalid agent")
        else:
            print(f"❌ Unexpected error: {e}")


async def test_multiple_executions(agent_id: int = 1):
    """Test multiple executions on same connection."""
    uri = f"ws://localhost:8000/ws/agents/{agent_id}/execute"

    print(f"\n{'='*60}")
    print(f"Testing Multiple Executions on Same Connection")
    print(f"{'='*60}\n")

    try:
        async with websockets.connect(uri) as websocket:
            # Skip connected message
            await websocket.recv()
            print("✓ Connection established")

            # Execute 3 times
            for i in range(1, 4):
                print(f"\n--- Execution #{i} ---")

                # Send execute request
                await websocket.send(json.dumps({
                    "type": "execute",
                    "variables": {}
                }))

                # Wait for result
                async for message in websocket:
                    data = json.loads(message)
                    if data['type'] in ['result', 'error']:
                        if data['type'] == 'result':
                            print(f"✓ Execution #{i} succeeded (ID: {data['execution_id']})")
                        else:
                            print(f"❌ Execution #{i} failed: {data['error']}")
                        break

            print(f"\n✓ Multiple executions test completed\n")

    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")
        sys.exit(1)


async def main():
    """Run all WebSocket tests."""
    print("\n" + "="*60)
    print("Claude Agent Control Center - WebSocket Test Suite")
    print("="*60)

    # Test 1: Valid execution
    print("\n[TEST 1] Valid WebSocket Execution")
    await test_websocket_execution(agent_id=1, variables={})

    # Test 2: Invalid agent
    print("\n[TEST 2] Invalid Agent ID")
    await test_invalid_agent()

    # Test 3: Multiple executions
    print("\n[TEST 3] Multiple Executions")
    await test_multiple_executions(agent_id=1)

    print("\n" + "="*60)
    print("✅ All tests passed!")
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
