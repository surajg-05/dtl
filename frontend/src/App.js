import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { format, formatDistanceToNow, parseISO, addHours } from 'date-fns';
import {
  Car, MapPin, Clock, Users, DollarSign, Search, Plus, LogOut,
  User, Check, X, AlertTriangle, Repeat, Zap, Navigation, ChevronRight,
  Filter, Star, Calendar
} from 'lucide-react';
import './App.css';

const API_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

// API instance with auth header
const api = axios.create({
  baseURL: API_URL,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth Context
const useAuth = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    if (token && userData) {
      setUser(JSON.parse(userData));
    }
    setLoading(false);
  }, []);

  const login = async (email, password) => {
    const response = await api.post('/api/auth/login', { email, password });
    localStorage.setItem('token', response.data.access_token);
    localStorage.setItem('user', JSON.stringify(response.data.user));
    setUser(response.data.user);
    return response.data;
  };

  const signup = async (email, password, name, role) => {
    const response = await api.post('/api/auth/signup', { email, password, name, role });
    localStorage.setItem('token', response.data.access_token);
    localStorage.setItem('user', JSON.stringify(response.data.user));
    setUser(response.data.user);
    return response.data;
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
  };

  return { user, loading, login, signup, logout };
};

// Components
const Badge = ({ variant, children, className = '' }) => {
  const variants = {
    urgent: 'bg-red-100 text-red-800 border-red-200',
    recommended: 'bg-green-100 text-green-800 border-green-200',
    recurring: 'bg-purple-100 text-purple-800 border-purple-200',
    pending: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    accepted: 'bg-green-100 text-green-800 border-green-200',
    rejected: 'bg-red-100 text-red-800 border-red-200',
    default: 'bg-gray-100 text-gray-800 border-gray-200'
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full border ${variants[variant] || variants.default} ${className}`} data-testid={`badge-${variant}`}>
      {children}
    </span>
  );
};

const LoadingSpinner = () => (
  <div className="flex justify-center items-center p-8" data-testid="loading-spinner">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
  </div>
);

// Auth Page
const AuthPage = ({ onLogin }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    name: '',
    role: 'rider'
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      if (isLogin) {
        await onLogin(formData.email, formData.password);
      } else {
        await onLogin(formData.email, formData.password, formData.name, formData.role, true);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-purple-700 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8" data-testid="auth-page">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Car className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">CampusPool</h1>
          <p className="text-gray-600 mt-1">Ride sharing for college students</p>
        </div>

        <div className="flex mb-6">
          <button
            onClick={() => setIsLogin(true)}
            className={`flex-1 py-2 text-center font-medium transition-colors ${
              isLogin ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500'
            }`}
            data-testid="login-tab"
          >
            Login
          </button>
          <button
            onClick={() => setIsLogin(false)}
            className={`flex-1 py-2 text-center font-medium transition-colors ${
              !isLogin ? 'text-blue-600 border-b-2 border-blue-600' : 'text-gray-500'
            }`}
            data-testid="signup-tab"
          >
            Sign Up
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4" data-testid="auth-error">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {!isLogin && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="input-field"
                placeholder="John Doe"
                required={!isLogin}
                data-testid="name-input"
              />
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="input-field"
              placeholder="you@college.edu"
              required
              data-testid="email-input"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              className="input-field"
              placeholder="••••••••"
              required
              minLength={6}
              data-testid="password-input"
            />
          </div>

          {!isLogin && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">I want to</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, role: 'rider' })}
                  className={`p-4 rounded-xl border-2 transition-all ${
                    formData.role === 'rider'
                      ? 'border-blue-600 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  data-testid="rider-role-btn"
                >
                  <Users className="w-6 h-6 mx-auto mb-2 text-blue-600" />
                  <span className="font-medium">Find Rides</span>
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, role: 'driver' })}
                  className={`p-4 rounded-xl border-2 transition-all ${
                    formData.role === 'driver'
                      ? 'border-blue-600 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  data-testid="driver-role-btn"
                >
                  <Car className="w-6 h-6 mx-auto mb-2 text-blue-600" />
                  <span className="font-medium">Offer Rides</span>
                </button>
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full btn-primary py-3 text-lg disabled:opacity-50"
            data-testid="auth-submit-btn"
          >
            {loading ? 'Please wait...' : (isLogin ? 'Login' : 'Create Account')}
          </button>
        </form>
      </div>
    </div>
  );
};

// Ride Card Component
const RideCard = ({ ride, onRequest, userRole, showRequestBtn = true }) => {
  const [isUrgent, setIsUrgent] = useState(false);
  const [requesting, setRequesting] = useState(false);
  
  const departureTime = parseISO(ride.departureTime);
  const hoursUntilDeparture = (departureTime - new Date()) / (1000 * 60 * 60);
  const canBeUrgent = hoursUntilDeparture <= 2 && hoursUntilDeparture > 0;

  const handleRequest = async () => {
    setRequesting(true);
    try {
      await onRequest(ride.id, isUrgent);
    } finally {
      setRequesting(false);
    }
  };

  return (
    <div className={`card hover:shadow-md transition-shadow ${ride.isRecommended ? 'ring-2 ring-green-500' : ''}`} data-testid={`ride-card-${ride.id}`}>
      <div className="flex flex-wrap gap-2 mb-3">
        {ride.isRecommended && (
          <Badge variant="recommended">
            <Star className="w-3 h-3 inline mr-1" />
            Recommended
          </Badge>
        )}
        {ride.isRecurring && (
          <Badge variant="recurring">
            <Repeat className="w-3 h-3 inline mr-1" />
            {ride.recurrencePattern || 'Recurring'}
          </Badge>
        )}
      </div>

      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-green-500"></div>
            <span className="font-medium text-gray-900">{ride.source}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-red-500"></div>
            <span className="font-medium text-gray-900">{ride.destination}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-blue-600">${ride.costPerRider}</div>
          <div className="text-xs text-gray-500">per seat</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
        <div className="flex items-center gap-2 text-gray-600">
          <Clock className="w-4 h-4" />
          <span>{format(departureTime, 'MMM d, h:mm a')}</span>
        </div>
        <div className="flex items-center gap-2 text-gray-600">
          <Users className="w-4 h-4" />
          <span>{ride.availableSeats} of {ride.totalSeats} seats</span>
        </div>
        {ride.pickupPoint && (
          <div className="flex items-center gap-2 text-gray-600 col-span-2">
            <Navigation className="w-4 h-4" />
            <span>Pickup: {ride.pickupPoint}</span>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
            <User className="w-4 h-4 text-blue-600" />
          </div>
          <span className="text-sm text-gray-700">{ride.driverName}</span>
        </div>
        
        {showRequestBtn && userRole === 'rider' && ride.availableSeats > 0 && (
          <div className="flex items-center gap-2">
            {canBeUrgent && (
              <label className="flex items-center gap-1 text-sm cursor-pointer" data-testid="urgent-toggle">
                <input
                  type="checkbox"
                  checked={isUrgent}
                  onChange={(e) => setIsUrgent(e.target.checked)}
                  className="rounded text-red-600 focus:ring-red-500"
                />
                <Zap className="w-4 h-4 text-red-500" />
                <span className="text-red-600 font-medium">Urgent</span>
              </label>
            )}
            <button
              onClick={handleRequest}
              disabled={requesting}
              className="btn-primary flex items-center gap-2"
              data-testid="request-ride-btn"
            >
              {requesting ? 'Requesting...' : 'Request Ride'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// Ride Search/Filter Component
const RideSearch = ({ onSearch, pickupPoints }) => {
  const [filters, setFilters] = useState({
    source: '',
    destination: '',
    timeWindowStart: '',
    timeWindowEnd: ''
  });
  const [showFilters, setShowFilters] = useState(false);

  const handleSearch = () => {
    onSearch(filters);
  };

  const handleReset = () => {
    setFilters({
      source: '',
      destination: '',
      timeWindowStart: '',
      timeWindowEnd: ''
    });
    onSearch({});
  };

  return (
    <div className="card mb-6" data-testid="ride-search">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 flex items-center gap-2">
          <Search className="w-5 h-5 text-blue-600" />
          Find Rides
        </h3>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-1 text-blue-600 text-sm font-medium"
          data-testid="toggle-filters-btn"
        >
          <Filter className="w-4 h-4" />
          {showFilters ? 'Hide' : 'Show'} Filters
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">From</label>
          <input
            type="text"
            value={filters.source}
            onChange={(e) => setFilters({ ...filters, source: e.target.value })}
            className="input-field"
            placeholder="Enter source location"
            data-testid="search-source-input"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">To</label>
          <input
            type="text"
            value={filters.destination}
            onChange={(e) => setFilters({ ...filters, destination: e.target.value })}
            className="input-field"
            placeholder="Enter destination"
            data-testid="search-destination-input"
          />
        </div>
      </div>

      {showFilters && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-gray-100">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Clock className="w-4 h-4 inline mr-1" />
              Time Window Start
            </label>
            <input
              type="datetime-local"
              value={filters.timeWindowStart}
              onChange={(e) => setFilters({ ...filters, timeWindowStart: e.target.value })}
              className="input-field"
              data-testid="time-start-input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Clock className="w-4 h-4 inline mr-1" />
              Time Window End
            </label>
            <input
              type="datetime-local"
              value={filters.timeWindowEnd}
              onChange={(e) => setFilters({ ...filters, timeWindowEnd: e.target.value })}
              className="input-field"
              data-testid="time-end-input"
            />
          </div>
        </div>
      )}

      <div className="flex gap-3 mt-4">
        <button
          onClick={handleSearch}
          className="btn-primary flex items-center gap-2"
          data-testid="search-btn"
        >
          <Search className="w-4 h-4" />
          Search Rides
        </button>
        <button
          onClick={handleReset}
          className="btn-secondary"
          data-testid="reset-search-btn"
        >
          Reset
        </button>
      </div>
    </div>
  );
};

// Post Ride Form
const PostRideForm = ({ pickupPoints, onSubmit, onCancel }) => {
  const [formData, setFormData] = useState({
    source: '',
    destination: '',
    departureTime: '',
    totalSeats: 3,
    estimatedCost: '',
    pickupPoint: '',
    isRecurring: false,
    recurrencePattern: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      const data = {
        ...formData,
        departure_time: new Date(formData.departureTime).toISOString(),
        total_seats: parseInt(formData.totalSeats),
        estimated_cost: parseFloat(formData.estimatedCost),
        pickup_point: formData.pickupPoint || null,
        is_recurring: formData.isRecurring,
        recurrence_pattern: formData.isRecurring ? formData.recurrencePattern : null
      };
      await onSubmit(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to post ride');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card" data-testid="post-ride-form">
      <h3 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-2">
        <Plus className="w-6 h-6 text-blue-600" />
        Post a New Ride
      </h3>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4" data-testid="post-ride-error">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">From *</label>
            <input
              type="text"
              value={formData.source}
              onChange={(e) => setFormData({ ...formData, source: e.target.value })}
              className="input-field"
              placeholder="Starting location"
              required
              data-testid="ride-source-input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">To *</label>
            <input
              type="text"
              value={formData.destination}
              onChange={(e) => setFormData({ ...formData, destination: e.target.value })}
              className="input-field"
              placeholder="Destination"
              required
              data-testid="ride-destination-input"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Departure Time *</label>
            <input
              type="datetime-local"
              value={formData.departureTime}
              onChange={(e) => setFormData({ ...formData, departureTime: e.target.value })}
              className="input-field"
              required
              data-testid="ride-time-input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <Navigation className="w-4 h-4 inline mr-1" />
              Pickup Point
            </label>
            <select
              value={formData.pickupPoint}
              onChange={(e) => setFormData({ ...formData, pickupPoint: e.target.value })}
              className="input-field"
              data-testid="pickup-point-select"
            >
              <option value="">Select pickup point (optional)</option>
              {pickupPoints.map((point) => (
                <option key={point} value={point}>{point}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Available Seats *</label>
            <input
              type="number"
              min="1"
              max="8"
              value={formData.totalSeats}
              onChange={(e) => setFormData({ ...formData, totalSeats: e.target.value })}
              className="input-field"
              required
              data-testid="ride-seats-input"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Estimated Cost ($) *</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={formData.estimatedCost}
              onChange={(e) => setFormData({ ...formData, estimatedCost: e.target.value })}
              className="input-field"
              placeholder="Total trip cost"
              required
              data-testid="ride-cost-input"
            />
          </div>
        </div>

        {/* Recurring Ride Options */}
        <div className="p-4 bg-purple-50 rounded-lg border border-purple-100">
          <label className="flex items-center gap-3 cursor-pointer mb-3" data-testid="recurring-toggle">
            <input
              type="checkbox"
              checked={formData.isRecurring}
              onChange={(e) => setFormData({ ...formData, isRecurring: e.target.checked })}
              className="w-5 h-5 rounded text-purple-600 focus:ring-purple-500"
            />
            <div className="flex items-center gap-2">
              <Repeat className="w-5 h-5 text-purple-600" />
              <span className="font-medium text-purple-900">Make this a recurring ride</span>
            </div>
          </label>
          
          {formData.isRecurring && (
            <div className="ml-8">
              <label className="block text-sm font-medium text-gray-700 mb-2">Recurrence Pattern</label>
              <div className="flex flex-wrap gap-3">
                {[
                  { value: 'weekdays', label: 'Weekdays', desc: '(Mon-Fri for 2 weeks)' },
                  { value: 'daily', label: 'Daily', desc: '(Next 7 days)' },
                  { value: 'weekly', label: 'Weekly', desc: '(Next 4 weeks)' }
                ].map((pattern) => (
                  <button
                    key={pattern.value}
                    type="button"
                    onClick={() => setFormData({ ...formData, recurrencePattern: pattern.value })}
                    className={`px-4 py-2 rounded-lg border-2 transition-all ${
                      formData.recurrencePattern === pattern.value
                        ? 'border-purple-600 bg-purple-100 text-purple-700'
                        : 'border-gray-200 hover:border-purple-300'
                    }`}
                    data-testid={`recurrence-${pattern.value}`}
                  >
                    <span className="font-medium">{pattern.label}</span>
                    <span className="text-xs text-gray-500 block">{pattern.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-3 pt-4">
          <button
            type="submit"
            disabled={loading}
            className="btn-primary flex items-center gap-2"
            data-testid="submit-ride-btn"
          >
            {loading ? 'Posting...' : 'Post Ride'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="btn-secondary"
            data-testid="cancel-post-btn"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
};

// Request Card Component
const RequestCard = ({ request, onAccept, onReject, isDriverView = false }) => {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action) => {
    setLoading(true);
    try {
      if (action === 'accept') {
        await onAccept(request.id);
      } else {
        await onReject(request.id);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`card ${request.isUrgent ? 'ring-2 ring-red-500' : ''}`} data-testid={`request-card-${request.id}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            {request.isUrgent && (
              <Badge variant="urgent">
                <Zap className="w-3 h-3 inline mr-1" />
                Urgent
              </Badge>
            )}
            <Badge variant={request.status}>{request.status}</Badge>
          </div>
          
          {isDriverView ? (
            <p className="font-medium text-gray-900">{request.riderName}</p>
          ) : (
            <div className="text-sm text-gray-600">
              <p><span className="font-medium">Route:</span> {request.ride?.source} → {request.ride?.destination}</p>
              <p><span className="font-medium">Driver:</span> {request.ride?.driverName}</p>
              {request.ride?.pickupPoint && (
                <p><span className="font-medium">Pickup:</span> {request.ride?.pickupPoint}</p>
              )}
            </div>
          )}
          
          <p className="text-xs text-gray-500 mt-2">
            {formatDistanceToNow(parseISO(request.createdAt), { addSuffix: true })}
          </p>
        </div>

        {isDriverView && request.status === 'pending' && (
          <div className="flex gap-2">
            <button
              onClick={() => handleAction('accept')}
              disabled={loading}
              className="p-2 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition-colors"
              data-testid="accept-request-btn"
            >
              <Check className="w-5 h-5" />
            </button>
            <button
              onClick={() => handleAction('reject')}
              disabled={loading}
              className="p-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors"
              data-testid="reject-request-btn"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// Main App Component
function App() {
  const auth = useAuth();
  const [view, setView] = useState('rides'); // rides, myRides, requests, post
  const [rides, setRides] = useState([]);
  const [myRides, setMyRides] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [pickupPoints, setPickupPoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);

  // Fetch pickup points
  const fetchPickupPoints = useCallback(async () => {
    try {
      const response = await api.get('/api/pickup-points');
      setPickupPoints(response.data.pickup_points);
    } catch (err) {
      console.error('Failed to fetch pickup points:', err);
    }
  }, []);

  // Fetch all rides
  const fetchRides = useCallback(async (filters = {}) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.source) params.append('source', filters.source);
      if (filters.destination) params.append('destination', filters.destination);
      if (filters.timeWindowStart) params.append('time_window_start', new Date(filters.timeWindowStart).toISOString());
      if (filters.timeWindowEnd) params.append('time_window_end', new Date(filters.timeWindowEnd).toISOString());
      
      const response = await api.get(`/api/rides?${params.toString()}`);
      setRides(response.data.rides);
    } catch (err) {
      showNotification('Failed to fetch rides', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch driver's rides
  const fetchMyRides = useCallback(async () => {
    try {
      const response = await api.get('/api/rides/driver/my-rides');
      setMyRides(response.data.rides);
    } catch (err) {
      console.error('Failed to fetch my rides:', err);
    }
  }, []);

  // Fetch rider's requests
  const fetchMyRequests = useCallback(async () => {
    try {
      const response = await api.get('/api/requests/my-requests');
      setMyRequests(response.data.requests);
    } catch (err) {
      console.error('Failed to fetch my requests:', err);
    }
  }, []);

  // Show notification
  const showNotification = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3000);
  };

  // Request a ride
  const requestRide = async (rideId, isUrgent = false) => {
    try {
      await api.post('/api/requests', { ride_id: rideId, is_urgent: isUrgent });
      showNotification(isUrgent ? 'Urgent ride request sent!' : 'Ride request sent!');
      fetchRides();
      fetchMyRequests();
    } catch (err) {
      showNotification(err.response?.data?.detail || 'Failed to request ride', 'error');
    }
  };

  // Post a ride
  const postRide = async (rideData) => {
    try {
      const response = await api.post('/api/rides', rideData);
      const msg = response.data.recurring_rides_created > 0
        ? `Ride posted! ${response.data.recurring_rides_created} recurring rides created.`
        : 'Ride posted successfully!';
      showNotification(msg);
      setView('myRides');
      fetchMyRides();
    } catch (err) {
      throw err;
    }
  };

  // Accept request
  const acceptRequest = async (requestId) => {
    try {
      await api.patch(`/api/requests/${requestId}/accept`);
      showNotification('Request accepted!');
      fetchMyRides();
    } catch (err) {
      showNotification(err.response?.data?.detail || 'Failed to accept request', 'error');
    }
  };

  // Reject request
  const rejectRequest = async (requestId) => {
    try {
      await api.patch(`/api/requests/${requestId}/reject`);
      showNotification('Request rejected');
      fetchMyRides();
    } catch (err) {
      showNotification(err.response?.data?.detail || 'Failed to reject request', 'error');
    }
  };

  // Auth handlers
  const handleLogin = async (email, password, name, role, isSignup = false) => {
    if (isSignup) {
      await auth.signup(email, password, name, role);
    } else {
      await auth.login(email, password);
    }
  };

  // Initial data fetch
  useEffect(() => {
    if (auth.user) {
      fetchPickupPoints();
      fetchRides();
      if (auth.user.role === 'driver') {
        fetchMyRides();
      } else {
        fetchMyRequests();
      }
    }
  }, [auth.user, fetchPickupPoints, fetchRides, fetchMyRides, fetchMyRequests]);

  if (auth.loading) {
    return <LoadingSpinner />;
  }

  if (!auth.user) {
    return <AuthPage onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-gray-50" data-testid="main-app">
      {/* Header */}
      <header className="bg-white shadow-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
              <Car className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">CampusPool</h1>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                <User className="w-4 h-4 text-blue-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">{auth.user.name}</p>
                <p className="text-xs text-gray-500 capitalize">{auth.user.role}</p>
              </div>
            </div>
            <button
              onClick={auth.logout}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              data-testid="logout-btn"
            >
              <LogOut className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Notification */}
      {notification && (
        <div
          className={`fixed top-20 right-4 z-50 px-6 py-3 rounded-lg shadow-lg ${
            notification.type === 'error' ? 'bg-red-600' : 'bg-green-600'
          } text-white font-medium`}
          data-testid="notification"
        >
          {notification.message}
        </div>
      )}

      {/* Navigation */}
      <nav className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex gap-1">
            <button
              onClick={() => { setView('rides'); fetchRides(); }}
              className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                view === 'rides' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              data-testid="nav-rides"
            >
              <Search className="w-4 h-4 inline mr-2" />
              Find Rides
            </button>
            
            {auth.user.role === 'driver' && (
              <>
                <button
                  onClick={() => { setView('myRides'); fetchMyRides(); }}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                    view === 'myRides' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                  data-testid="nav-my-rides"
                >
                  <Car className="w-4 h-4 inline mr-2" />
                  My Rides
                </button>
                <button
                  onClick={() => setView('post')}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                    view === 'post' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                  data-testid="nav-post-ride"
                >
                  <Plus className="w-4 h-4 inline mr-2" />
                  Post Ride
                </button>
              </>
            )}
            
            {auth.user.role === 'rider' && (
              <button
                onClick={() => { setView('requests'); fetchMyRequests(); }}
                className={`px-4 py-3 font-medium transition-colors border-b-2 ${
                  view === 'requests' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
                data-testid="nav-my-requests"
              >
                <Calendar className="w-4 h-4 inline mr-2" />
                My Requests
              </button>
            )}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        {/* Find Rides View */}
        {view === 'rides' && (
          <div>
            <RideSearch onSearch={fetchRides} pickupPoints={pickupPoints} />
            
            {loading ? (
              <LoadingSpinner />
            ) : rides.length === 0 ? (
              <div className="card text-center py-12">
                <Car className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No rides found</h3>
                <p className="text-gray-500">Try adjusting your search filters or check back later</p>
              </div>
            ) : (
              <div className="space-y-4">
                {rides.filter(r => r.isRecommended).length > 0 && (
                  <div className="mb-2">
                    <h3 className="text-sm font-medium text-green-700 mb-3 flex items-center gap-2">
                      <Star className="w-4 h-4" />
                      Recommended for you
                    </h3>
                  </div>
                )}
                {rides.map((ride) => (
                  <RideCard
                    key={ride.id}
                    ride={ride}
                    onRequest={requestRide}
                    userRole={auth.user.role}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* My Rides View (Driver) */}
        {view === 'myRides' && auth.user.role === 'driver' && (
          <div>
            <h2 className="text-xl font-bold text-gray-900 mb-6">My Posted Rides</h2>
            
            {myRides.length === 0 ? (
              <div className="card text-center py-12">
                <Car className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No rides posted yet</h3>
                <p className="text-gray-500 mb-4">Start sharing rides with fellow students</p>
                <button
                  onClick={() => setView('post')}
                  className="btn-primary"
                  data-testid="post-first-ride-btn"
                >
                  Post Your First Ride
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {myRides.map((ride) => (
                  <DriverRideCard
                    key={ride.id}
                    ride={ride}
                    onAccept={acceptRequest}
                    onReject={rejectRequest}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* My Requests View (Rider) */}
        {view === 'requests' && auth.user.role === 'rider' && (
          <div>
            <h2 className="text-xl font-bold text-gray-900 mb-6">My Ride Requests</h2>
            
            {myRequests.length === 0 ? (
              <div className="card text-center py-12">
                <Calendar className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No requests yet</h3>
                <p className="text-gray-500 mb-4">Browse available rides and send requests</p>
                <button
                  onClick={() => setView('rides')}
                  className="btn-primary"
                  data-testid="find-rides-btn"
                >
                  Find Rides
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {myRequests.map((request) => (
                  <RequestCard key={request.id} request={request} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Post Ride View */}
        {view === 'post' && auth.user.role === 'driver' && (
          <PostRideForm
            pickupPoints={pickupPoints}
            onSubmit={postRide}
            onCancel={() => setView('myRides')}
          />
        )}
      </main>
    </div>
  );
}

// Driver Ride Card with request management
const DriverRideCard = ({ ride, onAccept, onReject }) => {
  const [requests, setRequests] = useState([]);
  const [showRequests, setShowRequests] = useState(false);
  const [loadingRequests, setLoadingRequests] = useState(false);

  const fetchRequests = async () => {
    setLoadingRequests(true);
    try {
      const response = await api.get(`/api/requests/ride/${ride.id}`);
      setRequests(response.data.requests);
    } catch (err) {
      console.error('Failed to fetch requests:', err);
    } finally {
      setLoadingRequests(false);
    }
  };

  const handleToggleRequests = () => {
    if (!showRequests) {
      fetchRequests();
    }
    setShowRequests(!showRequests);
  };

  const departureTime = parseISO(ride.departureTime);
  const pendingCount = requests.filter(r => r.status === 'pending').length;
  const urgentCount = requests.filter(r => r.isUrgent && r.status === 'pending').length;

  return (
    <div className="card" data-testid={`driver-ride-card-${ride.id}`}>
      <div className="flex flex-wrap gap-2 mb-3">
        {ride.isRecurring && (
          <Badge variant="recurring">
            <Repeat className="w-3 h-3 inline mr-1" />
            {ride.recurrencePattern || 'Recurring'}
          </Badge>
        )}
        <Badge variant={ride.status}>{ride.status}</Badge>
      </div>

      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-green-500"></div>
            <span className="font-medium text-gray-900">{ride.source}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-red-500"></div>
            <span className="font-medium text-gray-900">{ride.destination}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-blue-600">${ride.estimatedCost}</div>
          <div className="text-xs text-gray-500">total cost</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
        <div className="flex items-center gap-2 text-gray-600">
          <Clock className="w-4 h-4" />
          <span>{format(departureTime, 'MMM d, h:mm a')}</span>
        </div>
        <div className="flex items-center gap-2 text-gray-600">
          <Users className="w-4 h-4" />
          <span>{ride.availableSeats} of {ride.totalSeats} seats available</span>
        </div>
        {ride.pickupPoint && (
          <div className="flex items-center gap-2 text-gray-600 col-span-2">
            <Navigation className="w-4 h-4" />
            <span>Pickup: {ride.pickupPoint}</span>
          </div>
        )}
      </div>

      <button
        onClick={handleToggleRequests}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
        data-testid="toggle-requests-btn"
      >
        <div className="flex items-center gap-2">
          <Users className="w-5 h-5 text-gray-500" />
          <span className="font-medium">Ride Requests</span>
          {urgentCount > 0 && (
            <Badge variant="urgent">{urgentCount} urgent</Badge>
          )}
        </div>
        <ChevronRight className={`w-5 h-5 text-gray-400 transition-transform ${showRequests ? 'rotate-90' : ''}`} />
      </button>

      {showRequests && (
        <div className="mt-4 space-y-3">
          {loadingRequests ? (
            <LoadingSpinner />
          ) : requests.length === 0 ? (
            <p className="text-gray-500 text-center py-4">No requests yet</p>
          ) : (
            requests.map((request) => (
              <RequestCard
                key={request.id}
                request={request}
                isDriverView={true}
                onAccept={onAccept}
                onReject={onReject}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default App;
