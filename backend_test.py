#!/usr/bin/env python3
"""
CampusPool Phase 6 Backend API Testing
Tests rating system, trust labels, ride history, and safe completion features
"""

import requests
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class CampusPoolTester:
    def __init__(self, base_url: str = "https://campuspool-community.preview.emergentagent.com"):
        self.base_url = base_url
        self.driver_token = None
        self.rider_token = None
        self.driver_id = None
        self.rider_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_ride_id = None
        self.test_request_id = None

    def log_test(self, name: str, success: bool, details: str = ""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED {details}")
        else:
            print(f"❌ {name} - FAILED {details}")
        return success

    def make_request(self, method: str, endpoint: str, data: Dict = None, token: str = None, expected_status: int = 200) -> tuple[bool, Dict]:
        """Make API request with error handling"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=10)
            else:
                return False, {"error": f"Unsupported method: {method}"}

            success = response.status_code == expected_status
            try:
                response_data = response.json()
            except:
                response_data = {"status_code": response.status_code, "text": response.text}

            return success, response_data

        except requests.exceptions.RequestException as e:
            return False, {"error": str(e)}

    def test_health_check(self) -> bool:
        """Test API health endpoint"""
        success, data = self.make_request('GET', '/health')
        return self.log_test("Health Check", success, f"- {data.get('status', 'unknown')}")

    def test_driver_login(self) -> bool:
        """Test driver login with provided credentials"""
        login_data = {
            "email": "testdriver@campus.edu",
            "password": "password123"
        }
        success, data = self.make_request('POST', '/auth/login', login_data)
        
        if success and 'access_token' in data:
            self.driver_token = data['access_token']
            self.driver_id = data['user']['id']
            return self.log_test("Driver Login", True, f"- Token received, ID: {self.driver_id}")
        else:
            return self.log_test("Driver Login", False, f"- {data.get('detail', 'Unknown error')}")

    def test_rider_login(self) -> bool:
        """Test rider login with provided credentials"""
        login_data = {
            "email": "testrider@campus.edu", 
            "password": "password123"
        }
        success, data = self.make_request('POST', '/auth/login', login_data)
        
        if success and 'access_token' in data:
            self.rider_token = data['access_token']
            self.rider_id = data['user']['id']
            return self.log_test("Rider Login", True, f"- Token received, ID: {self.rider_id}")
        else:
            return self.log_test("Rider Login", False, f"- {data.get('detail', 'Unknown error')}")

    def test_get_user_profile(self) -> bool:
        """Test getting user profile with trust info"""
        success, data = self.make_request('GET', '/auth/me', token=self.driver_token)
        
        if success:
            trust_fields = ['totalRides', 'avgRating', 'ratingCount', 'trustLabel']
            has_trust_info = all(field in data for field in trust_fields)
            return self.log_test("User Profile with Trust Info", has_trust_info, 
                               f"- Trust Label: {data.get('trustLabel', 'missing')}, Rating: {data.get('avgRating', 'missing')}")
        else:
            return self.log_test("User Profile with Trust Info", False, f"- {data.get('detail', 'Unknown error')}")

    def test_post_ride(self) -> bool:
        """Test posting a ride as driver"""
        departure_time = (datetime.now() + timedelta(hours=2)).isoformat()
        ride_data = {
            "source": "Main Gate",
            "destination": "Downtown Mall",
            "departure_time": departure_time,
            "total_seats": 3,
            "estimated_cost": 15.0,
            "pickup_point": "Main Gate",
            "is_recurring": False
        }
        
        success, data = self.make_request('POST', '/rides', ride_data, self.driver_token, 201)
        
        if success and 'ride' in data:
            self.test_ride_id = data['ride']['id']
            return self.log_test("Post Ride", True, f"- Ride ID: {self.test_ride_id}")
        else:
            return self.log_test("Post Ride", False, f"- {data.get('detail', 'Unknown error')}")

    def test_request_ride(self) -> bool:
        """Test requesting a ride as rider"""
        if not self.test_ride_id:
            return self.log_test("Request Ride", False, "- No test ride available")
            
        request_data = {
            "ride_id": self.test_ride_id,
            "is_urgent": False
        }
        
        success, data = self.make_request('POST', '/requests', request_data, self.rider_token, 201)
        
        if success and 'request' in data:
            self.test_request_id = data['request']['id']
            return self.log_test("Request Ride", True, f"- Request ID: {self.test_request_id}")
        else:
            return self.log_test("Request Ride", False, f"- {data.get('detail', 'Unknown error')}")

    def test_accept_request(self) -> bool:
        """Test accepting a ride request as driver"""
        if not self.test_request_id:
            return self.log_test("Accept Request", False, "- No test request available")
            
        success, data = self.make_request('PATCH', f'/requests/{self.test_request_id}/accept', token=self.driver_token)
        return self.log_test("Accept Request", success, f"- {data.get('message', 'Request accepted')}")

    def test_complete_ride(self) -> bool:
        """Test marking ride as completed"""
        if not self.test_ride_id:
            return self.log_test("Complete Ride", False, "- No test ride available")
            
        success, data = self.make_request('PATCH', f'/rides/{self.test_ride_id}/status?status=completed', token=self.driver_token)
        return self.log_test("Complete Ride", success, f"- {data.get('message', 'Ride completed')}")

    def test_rating_system(self) -> bool:
        """Test rating system - rider rates driver"""
        if not self.test_ride_id or not self.driver_id:
            return self.log_test("Rating System", False, "- Missing ride or driver ID")
            
        rating_data = {
            "ride_id": self.test_ride_id,
            "rated_user_id": self.driver_id,
            "rating": 5,
            "feedback": "Great driver, very punctual!"
        }
        
        success, data = self.make_request('POST', '/ratings', rating_data, self.rider_token, 201)
        return self.log_test("Rating System (Rider rates Driver)", success, f"- {data.get('message', 'Rating submitted')}")

    def test_driver_rating_rider(self) -> bool:
        """Test driver rating rider"""
        if not self.test_ride_id or not self.rider_id:
            return self.log_test("Driver Rating Rider", False, "- Missing ride or rider ID")
            
        rating_data = {
            "ride_id": self.test_ride_id,
            "rated_user_id": self.rider_id,
            "rating": 4,
            "feedback": "Good passenger, on time!"
        }
        
        success, data = self.make_request('POST', '/ratings', rating_data, self.driver_token, 201)
        return self.log_test("Driver Rating Rider", success, f"- {data.get('message', 'Rating submitted')}")

    def test_safe_completion(self) -> bool:
        """Test safe completion confirmation by rider"""
        if not self.test_ride_id:
            return self.log_test("Safe Completion", False, "- No test ride available")
            
        completion_data = {
            "ride_id": self.test_ride_id
        }
        
        success, data = self.make_request('POST', '/safe-completion', completion_data, self.rider_token, 201)
        return self.log_test("Safe Completion", success, f"- {data.get('message', 'Safe completion confirmed')}")

    def test_ride_history_driver(self) -> bool:
        """Test driver ride history endpoint"""
        success, data = self.make_request('GET', '/history/driver', token=self.driver_token)
        
        if success and 'history' in data:
            history_count = len(data['history'])
            return self.log_test("Driver Ride History", True, f"- {history_count} rides in history")
        else:
            return self.log_test("Driver Ride History", False, f"- {data.get('detail', 'Unknown error')}")

    def test_ride_history_rider(self) -> bool:
        """Test rider ride history endpoint"""
        success, data = self.make_request('GET', '/history/rider', token=self.rider_token)
        
        if success and 'history' in data:
            history_count = len(data['history'])
            return self.log_test("Rider Ride History", True, f"- {history_count} rides in history")
        else:
            return self.log_test("Rider Ride History", False, f"- {data.get('detail', 'Unknown error')}")

    def test_trust_calculation(self) -> bool:
        """Test trust label calculation after rating"""
        success, data = self.make_request('GET', '/auth/me', token=self.driver_token)
        
        if success:
            trust_label = data.get('trustLabel', 'unknown')
            avg_rating = data.get('avgRating', 0)
            total_rides = data.get('totalRides', 0)
            
            # Check if trust calculation makes sense
            trust_valid = trust_label in ['new_user', 'regular', 'trusted', 'low_rating']
            return self.log_test("Trust Calculation", trust_valid, 
                               f"- Label: {trust_label}, Rating: {avg_rating}, Rides: {total_rides}")
        else:
            return self.log_test("Trust Calculation", False, f"- {data.get('detail', 'Unknown error')}")

    def test_get_rides_with_trust(self) -> bool:
        """Test getting rides with driver trust information"""
        success, data = self.make_request('GET', '/rides')
        
        if success and 'rides' in data:
            rides = data['rides']
            if rides:
                first_ride = rides[0]
                has_trust_info = 'driverTrust' in first_ride
                return self.log_test("Rides with Trust Info", has_trust_info, 
                                   f"- {len(rides)} rides, trust info present: {has_trust_info}")
            else:
                return self.log_test("Rides with Trust Info", True, "- No rides available (expected)")
        else:
            return self.log_test("Rides with Trust Info", False, f"- {data.get('detail', 'Unknown error')}")

    def run_all_tests(self):
        """Run all backend tests in sequence"""
        print("🚀 Starting CampusPool Phase 6 Backend Tests")
        print("=" * 60)
        
        # Basic connectivity
        if not self.test_health_check():
            print("❌ Health check failed - stopping tests")
            return False
            
        # Authentication tests
        if not self.test_driver_login():
            print("❌ Driver login failed - stopping tests")
            return False
            
        if not self.test_rider_login():
            print("❌ Rider login failed - stopping tests") 
            return False
            
        # Profile and trust info
        self.test_get_user_profile()
        
        # Core ride flow
        self.test_post_ride()
        self.test_request_ride()
        self.test_accept_request()
        self.test_complete_ride()
        
        # Phase 6 features
        self.test_rating_system()
        self.test_driver_rating_rider()
        self.test_safe_completion()
        self.test_ride_history_driver()
        self.test_ride_history_rider()
        self.test_trust_calculation()
        self.test_get_rides_with_trust()
        
        # Summary
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        success_rate = (self.tests_passed / self.tests_run) * 100 if self.tests_run > 0 else 0
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("🎉 Backend tests mostly successful!")
            return True
        else:
            print("⚠️  Backend has significant issues")
            return False

def main():
    """Main test execution"""
    tester = CampusPoolTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())