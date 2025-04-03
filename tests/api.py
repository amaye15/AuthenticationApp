import asyncio
import aiohttp
import time
import argparse
from faker import Faker


class AuthClient:
    """
    Asynchronous Python client for interacting with the Authentication API
    """
    
    def __init__(self, base_url="http://localhost:7860/api"):
        """
        Initialize the client with the API base URL
        
        Args:
            base_url (str): The base URL of the API
        """
        self.base_url = base_url
        self.token = None
        self.session = None
    
    async def __aenter__(self):
        """Create and enter an aiohttp session"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
    
    async def _get_session(self):
        """Get or create an aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def register(self, email, password):
        """
        Register a new user
        
        Args:
            email (str): User's email
            password (str): User's password (should be at least 8 characters)
            
        Returns:
            dict: The user data returned by the API
            
        Raises:
            Exception: If registration fails
        """
        url = f"{self.base_url}/register"
        data = {
            "email": email,
            "password": password
        }
        
        session = await self._get_session()
        async with session.post(url, json=data) as response:
            if response.status == 201:
                return await response.json()
            else:
                error_data = await response.json()
                error_detail = error_data.get("detail", "Unknown error")
                raise Exception(f"Registration failed: {error_detail} (Status: {response.status})")
    
    async def login(self, email, password):
        """
        Login to obtain an authentication token
        
        Args:
            email (str): User's email
            password (str): User's password
            
        Returns:
            dict: The token data returned by the API
            
        Raises:
            Exception: If login fails
        """
        url = f"{self.base_url}/login"
        data = {
            "email": email,
            "password": password
        }
        
        session = await self._get_session()
        async with session.post(url, json=data) as response:
            if response.status == 200:
                token_data = await response.json()
                self.token = token_data["access_token"]
                return token_data
            else:
                error_data = await response.json()
                error_detail = error_data.get("detail", "Unknown error")
                raise Exception(f"Login failed: {error_detail} (Status: {response.status})")
    
    async def get_current_user(self):
        """
        Get information about the current logged-in user
        
        Returns:
            dict: The user data returned by the API
            
        Raises:
            Exception: If not authenticated or request fails
        """
        if not self.token:
            raise Exception("Not authenticated. Please login first.")
        
        url = f"{self.base_url}/users/me"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        session = await self._get_session()
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_data = await response.json()
                error_detail = error_data.get("detail", "Unknown error")
                raise Exception(f"Failed to get user info: {error_detail} (Status: {response.status})")
    
    def logout(self):
        """Clear the authentication token"""
        self.token = None


async def load_test(num_users=10, concurrency=5, base_url="http://localhost:7860/api"):
    """
    Run a load test with multiple simulated users
    
    Args:
        num_users (int): Total number of users to simulate
        concurrency (int): Number of concurrent users
        base_url (str): The base URL of the API
    """
    fake = Faker()
    
    start_time = time.time()
    completed = 0
    success_count = 0
    failure_count = 0
    
    # Semaphore to limit concurrency
    sem = asyncio.Semaphore(concurrency)
    
    # For progress tracking
    progress_lock = asyncio.Lock()
    
    async def run_single_user():
        nonlocal completed, success_count, failure_count
        
        async with sem:  # This limits concurrency
            async with AuthClient(base_url) as client:
                try:
                    # Generate random user data
                    email = fake.email()
                    password = fake.password(length=12, special_chars=True, digits=True, 
                                          upper_case=True, lower_case=True)
                    
                    # Complete user flow
                    await client.register(email, password)
                    await client.login(email, password)
                    await client.get_current_user()
                    client.logout()
                    
                    async with progress_lock:
                        completed += 1
                        success_count += 1
                        # Print progress
                        print(f"Progress: {completed}/{num_users} users completed", end="\r")
                        
                except Exception as e:
                    async with progress_lock:
                        completed += 1
                        failure_count += 1
                        print(f"Error: {e}")
                        print(f"Progress: {completed}/{num_users} users completed", end="\r")
    
    # Create all tasks
    tasks = [run_single_user() for _ in range(num_users)]
    
    # Display start message
    print(f"Starting load test with {num_users} users (max {concurrency} concurrent)...")
    
    # Run all tasks
    await asyncio.gather(*tasks)
    
    # Calculate stats
    end_time = time.time()
    duration = end_time - start_time
    
    # Display results
    print("\n\n--- Load Test Results ---")
    print(f"Total users: {num_users}")
    print(f"Concurrency level: {concurrency}")
    print(f"Successful flows: {success_count} ({success_count/num_users*100:.1f}%)")
    print(f"Failed flows: {failure_count} ({failure_count/num_users*100:.1f}%)")
    print(f"Total duration: {duration:.2f} seconds")
    
    if success_count > 0:
        print(f"Average time per successful user: {duration/success_count:.2f} seconds")
        print(f"Requests per second: {success_count/duration:.2f}")


async def single_user_test(base_url):
    """Run a test with a single user"""
    fake = Faker()
    async with AuthClient(base_url) as client:
        # Generate random user data
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = fake.email()
        password = fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)
        
        try:
            # Register a new user
            print(f"Registering a new user: {first_name} {last_name}...")
            user = await client.register(email, password)
            print(f"Registered user: {user}")
            
            # Login
            print("\nLogging in...")
            token_data = await client.login(email, password)
            print(f"Login successful, token: {token_data['access_token'][:10]}...")
            
            # Get current user
            print("\nGetting current user info...")
            user_info = await client.get_current_user()
            print(f"Current user: {user_info}")
            
            # Logout
            print("\nLogging out...")
            client.logout()
            print("Logged out successfully")
            
        except Exception as e:
            print(f"Error: {e}")


async def custom_user_test(email, password, base_url):
    """Test with specific user credentials"""
    async with AuthClient(base_url) as client:
        try:
            # Try to login first (for existing users)
            print(f"\nAttempting to login with email: {email}...")
            try:
                token_data = await client.login(email, password)
                print(f"Login successful, token: {token_data['access_token'][:10]}...")
            except Exception as e:
                print(f"Login failed: {e}")
                
                # If login fails, try to register
                print(f"\nAttempting to register with email: {email}...")
                user = await client.register(email, password)
                print(f"Registered user: {user}")
                
                # Now try login again after registration
                print("\nLogging in after registration...")
                token_data = await client.login(email, password)
                print(f"Login successful, token: {token_data['access_token'][:10]}...")
            
            # Get current user
            print("\nGetting current user info...")
            user_info = await client.get_current_user()
            print(f"Current user: {user_info}")
            
            # Logout
            print("\nLogging out...")
            client.logout()
            print("Logged out successfully")
            
        except Exception as e:
            print(f"Error: {e}")


async def main():
    # Define command-line arguments
    parser = argparse.ArgumentParser(description='Authentication API Client CLI')
    
    # Main command options
    parser.add_argument('--url', type=str, default="http://localhost:7860/api",
                        help='Base URL for the API (default: http://localhost:7860/api)')
    parser.add_argument('--remote', action='store_true',
                        help='Use the remote API endpoint')
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Single user test command
    single_parser = subparsers.add_parser('single', help='Run a test with a single random user')
    
    # Load test command
    load_parser = subparsers.add_parser('load', help='Run a load test with multiple users')
    load_parser.add_argument('--users', type=int, default=10, 
                             help='Number of users to simulate (default: 10)')
    load_parser.add_argument('--concurrency', type=int, default=5, 
                             help='Maximum number of concurrent users (default: 5)')
    
    # Custom user test command
    custom_parser = subparsers.add_parser('custom', help='Test with specific user credentials')
    custom_parser.add_argument('--email', type=str, required=True, help='User email')
    custom_parser.add_argument('--password', type=str, required=True, help='User password')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set remote URL if specified
    if args.remote:
        base_url = "https://amaye15-authenticationapp.hf.space/api"
        print(f"Using remote API at: {base_url}")
    else:
        base_url = args.url
        print(f"Using API at: {base_url}")
    
    # Execute the appropriate command
    if args.command == 'single':
        await single_user_test(base_url)
    elif args.command == 'load':
        await load_test(args.users, args.concurrency, base_url)
    elif args.command == 'custom':
        await custom_user_test(args.email, args.password, base_url)
    else:
        # If no command specified, show help
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())