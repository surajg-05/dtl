import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { format, formatDistanceToNow, parseISO } from 'date-fns';
import {
  Car, MapPin, Clock, Users, DollarSign, Search, Plus, LogOut,
  User, Check, X, AlertTriangle, Repeat, Zap, Navigation, ChevronRight,
  Filter, Star, Calendar, Shield, ShieldCheck, ShieldAlert, History,
  ThumbsUp, MessageSquare, Award, Leaf, TrendingUp, Target, Flame,
  Trophy, BookOpen, GraduationCap, Tag, BarChart3, ChevronDown
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

  const fetchUserInfo = async () => {
    try {
      const response = await api.get('/api/auth/me');
      setUser(response.data);
      localStorage.setItem('user', JSON.stringify(response.data));
    } catch (err) {
      console.error('Failed to fetch user info:', err);
    }
  };

  useEffect(() => {
    const token = localStorage.getItem('token');
    const userData = localStorage.getItem('user');
    if (token && userData) {
      setUser(JSON.parse(userData));
      fetchUserInfo();
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

  const signup = async (email, password, name, role, branch, academicYear) => {
    const response = await api.post('/api/auth/signup', { 
      email, password, name, role,
      branch: branch || null,
      academic_year: academicYear || null
    });
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

  return { user, loading, login, signup, logout, fetchUserInfo };
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
    completed: 'bg-blue-100 text-blue-800 border-blue-200',
    cancelled: 'bg-gray-100 text-gray-800 border-gray-200',
    trusted: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    new_user: 'bg-sky-100 text-sky-800 border-sky-200',
    low_rating: 'bg-orange-100 text-orange-800 border-orange-200',
    regular: 'bg-slate-100 text-slate-700 border-slate-200',
    event: 'bg-indigo-100 text-indigo-800 border-indigo-200',
    eco: 'bg-green-100 text-green-800 border-green-200',
    streak: 'bg-orange-100 text-orange-800 border-orange-200',
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

// Event Tag Badge Component
const EventTagBadge = ({ eventTag }) => {
  if (!eventTag) return null;
  
  return (
    <span 
      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full border"
      style={{ 
        backgroundColor: `${eventTag.color}20`,
        borderColor: eventTag.color,
        color: eventTag.color
      }}
      data-testid={`event-tag-${eventTag.id}`}
    >
      <span>{eventTag.icon}</span>
      {eventTag.name}
    </span>
  );
};

// Trust Badge Component
const TrustBadge = ({ trust, showRating = true, size = 'md' }) => {
  if (!trust) return null;
  
  const { trustLabel, avgRating, totalRides, ratingCount } = trust;
  
  const labelConfig = {
    trusted: { icon: ShieldCheck, text: 'Trusted', color: 'text-emerald-600' },
    new_user: { icon: Shield, text: 'New User', color: 'text-sky-600' },
    low_rating: { icon: ShieldAlert, text: 'Low Rating', color: 'text-orange-600' },
    regular: { icon: Shield, text: 'Regular', color: 'text-slate-600' }
  };

  const config = labelConfig[trustLabel] || labelConfig.regular;
  const Icon = config.icon;
  
  const sizeClasses = size === 'sm' ? 'text-xs' : 'text-sm';

  return (
    <div className={`flex items-center gap-2 ${sizeClasses}`} data-testid="trust-badge">
      <Badge variant={trustLabel}>
        <Icon className="w-3 h-3 inline mr-1" />
        {config.text}
      </Badge>
      {showRating && ratingCount > 0 && (
        <span className="flex items-center gap-1 text-gray-600">
          <Star className="w-3 h-3 text-yellow-500 fill-yellow-500" />
          {avgRating} ({ratingCount})
        </span>
      )}
      {totalRides > 0 && (
        <span className="text-gray-500">
          {totalRides} ride{totalRides !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  );
};

// Star Rating Input Component
const StarRatingInput = ({ rating, setRating, size = 'lg' }) => {
  const [hover, setHover] = useState(0);
  const sizeClass = size === 'lg' ? 'w-8 h-8' : 'w-5 h-5';
  
  return (
    <div className="flex gap-1" data-testid="star-rating-input">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          onClick={() => setRating(star)}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          className="focus:outline-none transition-transform hover:scale-110"
          data-testid={`star-${star}`}
        >
          <Star
            className={`${sizeClass} ${
              star <= (hover || rating)
                ? 'text-yellow-400 fill-yellow-400'
                : 'text-gray-300'
            }`}
          />
        </button>
      ))}
    </div>
  );
};

// Rating Modal Component
const RatingModal = ({ isOpen, onClose, rideId, userToRate, onSubmit }) => {
  const [rating, setRating] = useState(0);
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (rating === 0) {
      setError('Please select a rating');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      await onSubmit({
        ride_id: rideId,
        rated_user_id: userToRate.userId,
        rating,
        feedback: feedback.trim() || null
      });
      setRating(0);
      setFeedback('');
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit rating');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" data-testid="rating-modal">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
        <h3 className="text-xl font-bold text-gray-900 mb-2">Rate Your Experience</h3>
        <p className="text-gray-600 mb-6">How was your ride with {userToRate?.userName}?</p>
        
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4" data-testid="rating-error">
            {error}
          </div>
        )}
        
        <div className="flex justify-center mb-6">
          <StarRatingInput rating={rating} setRating={setRating} />
        </div>
        
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <MessageSquare className="w-4 h-4 inline mr-1" />
            Feedback (optional)
          </label>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            className="input-field h-24 resize-none"
            placeholder="Share your experience..."
            maxLength={500}
            data-testid="rating-feedback-input"
          />
        </div>
        
        <div className="flex gap-3">
          <button
            onClick={handleSubmit}
            disabled={loading || rating === 0}
            className="flex-1 btn-primary py-3 disabled:opacity-50"
            data-testid="submit-rating-btn"
          >
            {loading ? 'Submitting...' : 'Submit Rating'}
          </button>
          <button
            onClick={onClose}
            className="btn-secondary py-3"
            data-testid="cancel-rating-btn"
          >
            Later
          </button>
        </div>
      </div>
    </div>
  );
};

// Safe Completion Button Component
const SafeCompletionButton = ({ rideId, onConfirm, confirmed }) => {
  const [loading, setLoading] = useState(false);

  const handleConfirm = async () => {
    setLoading(true);
    try {
      await onConfirm(rideId);
    } finally {
      setLoading(false);
    }
  };

  if (confirmed) {
    return (
      <div className="flex items-center gap-2 text-green-600 bg-green-50 px-3 py-2 rounded-lg" data-testid="safe-confirmed">
        <ShieldCheck className="w-5 h-5" />
        <span className="font-medium">Reached Safely</span>
      </div>
    );
  }

  return (
    <button
      onClick={handleConfirm}
      disabled={loading}
      className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50"
      data-testid="confirm-safe-btn"
    >
      <ThumbsUp className="w-5 h-5" />
      {loading ? 'Confirming...' : 'Reached Safely'}
    </button>
  );
};

// User Badge Display Component
const UserBadgeDisplay = ({ badges, compact = false }) => {
  if (!badges || badges.length === 0) return null;
  
  const displayBadges = compact ? badges.slice(0, 3) : badges;
  
  return (
    <div className="flex flex-wrap gap-2" data-testid="user-badges">
      {displayBadges.map((badge) => (
        <div 
          key={badge.id}
          className="flex items-center gap-1 px-2 py-1 bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-200 rounded-full text-xs"
          title={badge.description}
        >
          <span>{badge.icon}</span>
          {!compact && <span className="font-medium text-amber-800">{badge.name}</span>}
        </div>
      ))}
      {compact && badges.length > 3 && (
        <span className="text-xs text-gray-500">+{badges.length - 3} more</span>
      )}
    </div>
  );
};

// Streak Display Component
const StreakDisplay = ({ streak }) => {
  if (!streak || streak.currentStreak === 0) return null;
  
  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-orange-50 border border-orange-200 rounded-lg" data-testid="streak-display">
      <Flame className="w-5 h-5 text-orange-500" />
      <div>
        <span className="font-bold text-orange-700">{streak.currentStreak}</span>
        <span className="text-orange-600 text-sm ml-1">day streak</span>
      </div>
      {streak.longestStreak > streak.currentStreak && (
        <span className="text-xs text-orange-500 ml-2">Best: {streak.longestStreak}</span>
      )}
    </div>
  );
};

// Eco Impact Card Component
const EcoImpactCard = ({ stats }) => {
  if (!stats) return null;
  
  const co2Saved = stats.co2SavedKg || 0;
  const treesEquivalent = (co2Saved / 21).toFixed(1);
  
  return (
    <div className="card bg-gradient-to-br from-green-50 to-emerald-50 border-green-200" data-testid="eco-impact-card">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 bg-green-500 rounded-xl flex items-center justify-center">
          <Leaf className="w-6 h-6 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-green-800">Your Eco Impact</h3>
          <p className="text-sm text-green-600">Making the planet greener</p>
        </div>
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-2xl font-bold text-green-700">{co2Saved.toFixed(1)}</div>
          <div className="text-xs text-green-600">kg CO₂ Saved</div>
        </div>
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-2xl font-bold text-green-700">{treesEquivalent}</div>
          <div className="text-xs text-green-600">🌳 Trees Equivalent</div>
        </div>
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-2xl font-bold text-green-700">{stats.totalDistanceKm || 0}</div>
          <div className="text-xs text-green-600">km Shared</div>
        </div>
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-2xl font-bold text-green-700">${stats.moneySaved?.toFixed(0) || 0}</div>
          <div className="text-xs text-green-600">Money Saved</div>
        </div>
      </div>
    </div>
  );
};

// Weekly Summary Card Component
const WeeklySummaryCard = ({ summary }) => {
  if (!summary) return null;
  
  return (
    <div className="card bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-200" data-testid="weekly-summary-card">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 bg-blue-500 rounded-xl flex items-center justify-center">
          <BarChart3 className="w-6 h-6 text-white" />
        </div>
        <div>
          <h3 className="font-bold text-blue-800">This Week</h3>
          <p className="text-sm text-blue-600">Your 7-day activity</p>
        </div>
      </div>
      
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-xl font-bold text-blue-700">{summary.totalRides}</div>
          <div className="text-xs text-blue-600">Rides</div>
        </div>
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-xl font-bold text-green-700">{summary.co2SavedKg?.toFixed(1)}</div>
          <div className="text-xs text-green-600">kg CO₂</div>
        </div>
        <div className="text-center p-3 bg-white bg-opacity-60 rounded-lg">
          <div className="text-xl font-bold text-amber-700">${summary.moneySaved?.toFixed(0)}</div>
          <div className="text-xs text-amber-600">Saved</div>
        </div>
      </div>
      
      <div className="mt-4 pt-4 border-t border-blue-200 flex justify-between text-sm">
        <span className="text-blue-600">Offered: {summary.ridesOffered}</span>
        <span className="text-blue-600">Taken: {summary.ridesTaken}</span>
        <span className="text-blue-600">{summary.distanceKm?.toFixed(0)} km</span>
      </div>
    </div>
  );
};

// Statistics Dashboard Component
const StatisticsDashboard = ({ user }) => {
  const [statistics, setStatistics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await api.get('/api/users/me/statistics');
        setStatistics(response.data);
      } catch (err) {
        console.error('Failed to fetch statistics:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) return <LoadingSpinner />;
  if (!statistics) return null;

  const { statistics: stats, streak, weeklySummary, badges } = statistics;

  return (
    <div className="space-y-6" data-testid="statistics-dashboard">
      {/* Header Stats */}
      <div className="card">
        <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-blue-600" />
          Your Statistics
        </h2>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-4 bg-blue-50 rounded-xl">
            <Car className="w-6 h-6 text-blue-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{stats.totalRides}</div>
            <div className="text-sm text-gray-600">Total Rides</div>
          </div>
          <div className="text-center p-4 bg-purple-50 rounded-xl">
            <Users className="w-6 h-6 text-purple-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{stats.ridesTaken}</div>
            <div className="text-sm text-gray-600">Rides Taken</div>
          </div>
          <div className="text-center p-4 bg-green-50 rounded-xl">
            <Car className="w-6 h-6 text-green-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{stats.ridesOffered}</div>
            <div className="text-sm text-gray-600">Rides Offered</div>
          </div>
          <div className="text-center p-4 bg-amber-50 rounded-xl">
            <Navigation className="w-6 h-6 text-amber-600 mx-auto mb-2" />
            <div className="text-2xl font-bold text-gray-900">{stats.totalDistanceKm}</div>
            <div className="text-sm text-gray-600">km Traveled</div>
          </div>
        </div>

        {/* Streak */}
        {streak && streak.currentStreak > 0 && (
          <div className="mt-4">
            <StreakDisplay streak={streak} />
          </div>
        )}
      </div>

      {/* Badges Section */}
      {badges && badges.length > 0 && (
        <div className="card">
          <h3 className="font-bold text-gray-900 mb-4 flex items-center gap-2">
            <Trophy className="w-5 h-5 text-amber-500" />
            Your Badges
          </h3>
          <UserBadgeDisplay badges={badges} />
        </div>
      )}

      {/* Eco Impact & Weekly Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <EcoImpactCard stats={stats} />
        <WeeklySummaryCard summary={weeklySummary} />
      </div>
    </div>
  );
};

// Auth Page
const AuthPage = ({ onLogin }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    name: '',
    role: 'rider',
    branch: '',
    academicYear: ''
  });
  const [academicOptions, setAcademicOptions] = useState({ branches: [], academic_years: [] });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchOptions = async () => {
      try {
        const response = await api.get('/api/academic-options');
        setAcademicOptions(response.data);
      } catch (err) {
        console.error('Failed to fetch academic options:', err);
      }
    };
    fetchOptions();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      if (isLogin) {
        await onLogin(formData.email, formData.password);
      } else {
        await onLogin(
          formData.email, 
          formData.password, 
          formData.name, 
          formData.role, 
          formData.branch,
          formData.academicYear,
          true
        );
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
            <>
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

              {/* Academic Info */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    <GraduationCap className="w-4 h-4 inline mr-1" />
                    Branch
                  </label>
                  <select
                    value={formData.branch}
                    onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                    className="input-field"
                    data-testid="branch-select"
                  >
                    <option value="">Select branch</option>
                    {academicOptions.branches.map((b) => (
                      <option key={b} value={b}>{b}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    <BookOpen className="w-4 h-4 inline mr-1" />
                    Year
                  </label>
                  <select
                    value={formData.academicYear}
                    onChange={(e) => setFormData({ ...formData, academicYear: e.target.value })}
                    className="input-field"
                    data-testid="year-select"
                  >
                    <option value="">Select year</option>
                    {academicOptions.academic_years.map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
              </div>
            </>
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
        {ride.eventTag && <EventTagBadge eventTag={ride.eventTag} />}
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
        {ride.distanceKm && (
          <div className="flex items-center gap-2 text-gray-600">
            <MapPin className="w-4 h-4" />
            <span>{ride.distanceKm} km</span>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
            <User className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <span className="text-sm text-gray-700 block">{ride.driverName}</span>
            {(ride.driverBranch || ride.driverYear) && (
              <span className="text-xs text-gray-500">
                {ride.driverBranch}{ride.driverBranch && ride.driverYear ? ' • ' : ''}{ride.driverYear}
              </span>
            )}
            {ride.driverTrust && (
              <TrustBadge trust={ride.driverTrust} size="sm" />
            )}
          </div>
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

// Ride Search/Filter Component with Community Filters
const RideSearch = ({ onSearch, pickupPoints, eventTags, academicOptions }) => {
  const [filters, setFilters] = useState({
    source: '',
    destination: '',
    timeWindowStart: '',
    timeWindowEnd: '',
    eventTag: '',
    branch: '',
    academicYear: ''
  });
  const [showFilters, setShowFilters] = useState(false);
  const [showCommunity, setShowCommunity] = useState(false);

  const handleSearch = () => {
    onSearch(filters);
  };

  const handleReset = () => {
    setFilters({
      source: '',
      destination: '',
      timeWindowStart: '',
      timeWindowEnd: '',
      eventTag: '',
      branch: '',
      academicYear: ''
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
        <div className="flex gap-2">
          <button
            onClick={() => setShowCommunity(!showCommunity)}
            className={`flex items-center gap-1 text-sm font-medium px-3 py-1 rounded-full ${
              showCommunity ? 'bg-purple-100 text-purple-700' : 'text-purple-600 hover:bg-purple-50'
            }`}
            data-testid="toggle-community-btn"
          >
            <Users className="w-4 h-4" />
            Community
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-1 text-blue-600 text-sm font-medium"
            data-testid="toggle-filters-btn"
          >
            <Filter className="w-4 h-4" />
            {showFilters ? 'Hide' : 'More'} Filters
          </button>
        </div>
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

      {/* Event Tag Filter */}
      {eventTags && eventTags.length > 0 && (
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            <Tag className="w-4 h-4 inline mr-1" />
            Filter by Event
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setFilters({ ...filters, eventTag: '' })}
              className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                !filters.eventTag 
                  ? 'bg-blue-100 border-blue-300 text-blue-700' 
                  : 'border-gray-200 hover:border-gray-300'
              }`}
              data-testid="event-all-btn"
            >
              All Events
            </button>
            {eventTags.map((tag) => (
              <button
                key={tag.id}
                onClick={() => setFilters({ ...filters, eventTag: tag.id })}
                className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                  filters.eventTag === tag.id 
                    ? 'border-2' 
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                style={filters.eventTag === tag.id ? { 
                  backgroundColor: `${tag.color}20`, 
                  borderColor: tag.color,
                  color: tag.color
                } : {}}
                data-testid={`event-filter-${tag.id}`}
              >
                {tag.icon} {tag.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Community Filters */}
      {showCommunity && (
        <div className="mt-4 p-4 bg-purple-50 rounded-lg border border-purple-200">
          <h4 className="font-medium text-purple-800 mb-3 flex items-center gap-2">
            <GraduationCap className="w-4 h-4" />
            Find Rides from Your Community
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Branch</label>
              <select
                value={filters.branch}
                onChange={(e) => setFilters({ ...filters, branch: e.target.value })}
                className="input-field"
                data-testid="filter-branch-select"
              >
                <option value="">All Branches</option>
                {academicOptions?.branches?.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Academic Year</label>
              <select
                value={filters.academicYear}
                onChange={(e) => setFilters({ ...filters, academicYear: e.target.value })}
                className="input-field"
                data-testid="filter-year-select"
              >
                <option value="">All Years</option>
                {academicOptions?.academic_years?.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

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

// Post Ride Form with Event Tag
const PostRideForm = ({ pickupPoints, eventTags, onSubmit, onCancel }) => {
  const [formData, setFormData] = useState({
    source: '',
    destination: '',
    departureTime: '',
    totalSeats: 3,
    estimatedCost: '',
    pickupPoint: '',
    isRecurring: false,
    recurrencePattern: '',
    eventTag: '',
    distanceKm: ''
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
        recurrence_pattern: formData.isRecurring ? formData.recurrencePattern : null,
        event_tag: formData.eventTag || null,
        distance_km: formData.distanceKm ? parseFloat(formData.distanceKm) : null
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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <MapPin className="w-4 h-4 inline mr-1" />
              Distance (km)
            </label>
            <input
              type="number"
              min="0"
              step="0.1"
              value={formData.distanceKm}
              onChange={(e) => setFormData({ ...formData, distanceKm: e.target.value })}
              className="input-field"
              placeholder="Approx distance"
              data-testid="ride-distance-input"
            />
          </div>
        </div>

        {/* Event Tag Selection */}
        {eventTags && eventTags.length > 0 && (
          <div className="p-4 bg-indigo-50 rounded-lg border border-indigo-100">
            <label className="block text-sm font-medium text-indigo-800 mb-3">
              <Tag className="w-4 h-4 inline mr-1" />
              Tag this ride with an event (optional)
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setFormData({ ...formData, eventTag: '' })}
                className={`px-3 py-2 rounded-lg border-2 transition-all ${
                  !formData.eventTag 
                    ? 'border-indigo-600 bg-indigo-100 text-indigo-700' 
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                data-testid="event-none-btn"
              >
                No Event
              </button>
              {eventTags.map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => setFormData({ ...formData, eventTag: tag.id })}
                  className={`px-3 py-2 rounded-lg border-2 transition-all ${
                    formData.eventTag === tag.id 
                      ? 'border-2' 
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  style={formData.eventTag === tag.id ? {
                    backgroundColor: `${tag.color}20`,
                    borderColor: tag.color,
                    color: tag.color
                  } : {}}
                  data-testid={`event-select-${tag.id}`}
                >
                  {tag.icon} {tag.name}
                </button>
              ))}
            </div>
          </div>
        )}

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
const RequestCard = ({ request, onAccept, onReject, isDriverView = false, onRate, onConfirmSafe }) => {
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

  const showRatingPrompt = request.pendingRating && request.ride?.status === 'completed';
  const showSafeConfirm = request.status === 'accepted' && request.ride?.status === 'completed' && !request.safelyConfirmed;

  return (
    <div className={`card ${request.isUrgent ? 'ring-2 ring-red-500' : ''}`} data-testid={`request-card-${request.id}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            {request.isUrgent && (
              <Badge variant="urgent">
                <Zap className="w-3 h-3 inline mr-1" />
                Urgent
              </Badge>
            )}
            <Badge variant={request.status}>{request.status}</Badge>
            {request.ride?.status === 'completed' && (
              <Badge variant="completed">
                <Check className="w-3 h-3 inline mr-1" />
                Completed
              </Badge>
            )}
          </div>
          
          {isDriverView ? (
            <div>
              <p className="font-medium text-gray-900">{request.riderName}</p>
              {(request.riderBranch || request.riderYear) && (
                <p className="text-xs text-gray-500">
                  {request.riderBranch}{request.riderBranch && request.riderYear ? ' • ' : ''}{request.riderYear}
                </p>
              )}
              {request.riderTrust && (
                <TrustBadge trust={request.riderTrust} size="sm" />
              )}
            </div>
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

      {/* Show actions for completed rides */}
      {(showRatingPrompt || showSafeConfirm) && (
        <div className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap gap-3">
          {showSafeConfirm && (
            <SafeCompletionButton
              rideId={request.rideId}
              onConfirm={onConfirmSafe}
              confirmed={request.safelyConfirmed}
            />
          )}
          {showRatingPrompt && (
            <button
              onClick={() => onRate(request.rideId, request.pendingRating)}
              className="flex items-center gap-2 bg-yellow-100 text-yellow-800 px-4 py-2 rounded-lg hover:bg-yellow-200 transition-colors"
              data-testid="rate-driver-btn"
            >
              <Star className="w-5 h-5" />
              Rate Driver
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// Ride History Card Component
const HistoryCard = ({ ride }) => {
  const departureTime = parseISO(ride.departureTime);

  return (
    <div className="card" data-testid={`history-card-${ride.id}`}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={ride.status}>{ride.status}</Badge>
            <Badge variant={ride.role === 'driver' ? 'recurring' : 'recommended'}>
              {ride.role === 'driver' ? 'As Driver' : 'As Rider'}
            </Badge>
            {ride.safelyConfirmed && (
              <Badge variant="trusted">
                <ShieldCheck className="w-3 h-3 inline mr-1" />
                Safe
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-green-500"></div>
            <span className="font-medium text-gray-900">{ride.source}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-red-500"></div>
            <span className="font-medium text-gray-900">{ride.destination}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-blue-600">
            ${ride.role === 'driver' ? ride.estimatedCost : ride.costPaid}
          </div>
          <div className="text-xs text-gray-500">
            {ride.role === 'driver' ? 'total earned' : 'paid'}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm text-gray-600">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4" />
          <span>{format(departureTime, 'MMM d, yyyy h:mm a')}</span>
        </div>
        {ride.distanceKm && (
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4" />
            <span>{ride.distanceKm} km</span>
          </div>
        )}
        {ride.role === 'driver' && (
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4" />
            <span>{ride.ridersCount} rider{ride.ridersCount !== 1 ? 's' : ''}</span>
          </div>
        )}
        {ride.role === 'rider' && ride.driverName && (
          <div className="flex items-center gap-2">
            <User className="w-4 h-4" />
            <span>{ride.driverName}</span>
          </div>
        )}
      </div>
    </div>
  );
};

// User Profile Card Component with Badges
const ProfileCard = ({ user, onLogout, onUpdateProfile }) => {
  const [editing, setEditing] = useState(false);
  const [academicOptions, setAcademicOptions] = useState({ branches: [], academic_years: [] });
  const [formData, setFormData] = useState({
    branch: user.branch || '',
    academicYear: user.academicYear || ''
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const fetchOptions = async () => {
      try {
        const response = await api.get('/api/academic-options');
        setAcademicOptions(response.data);
      } catch (err) {
        console.error('Failed to fetch academic options:', err);
      }
    };
    fetchOptions();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onUpdateProfile(formData);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="profile-card">
      <div className="card">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
            <User className="w-8 h-8 text-blue-600" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">{user.name}</h2>
            <p className="text-gray-600 capitalize">{user.role}</p>
            {(user.branch || user.academicYear) && (
              <p className="text-sm text-gray-500">
                {user.branch}{user.branch && user.academicYear ? ' • ' : ''}{user.academicYear}
              </p>
            )}
          </div>
        </div>

        {/* Badges */}
        {user.badges && user.badges.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
              <Trophy className="w-4 h-4 text-amber-500" />
              Your Badges
            </h3>
            <UserBadgeDisplay badges={user.badges} />
          </div>
        )}

        {/* Streak */}
        {user.streak && user.streak.currentStreak > 0 && (
          <div className="mb-6">
            <StreakDisplay streak={user.streak} />
          </div>
        )}

        {user.avgRating !== undefined && (
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-center gap-1 mb-1">
                <Star className="w-5 h-5 text-yellow-500 fill-yellow-500" />
                <span className="text-xl font-bold text-gray-900">{user.avgRating || '-'}</span>
              </div>
              <p className="text-xs text-gray-500">Rating</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <div className="text-xl font-bold text-gray-900">{user.totalRides || 0}</div>
              <p className="text-xs text-gray-500">Rides</p>
            </div>
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <div className="text-xl font-bold text-gray-900">{user.ratingCount || 0}</div>
              <p className="text-xs text-gray-500">Reviews</p>
            </div>
          </div>
        )}

        {user.trustLabel && (
          <div className="mb-6">
            <TrustBadge trust={user} showRating={false} />
          </div>
        )}

        {/* Academic Info Editor */}
        {editing ? (
          <div className="space-y-4 mb-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="font-medium text-gray-900">Edit Academic Info</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Branch</label>
                <select
                  value={formData.branch}
                  onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                  className="input-field"
                  data-testid="edit-branch-select"
                >
                  <option value="">Select branch</option>
                  {academicOptions.branches.map((b) => (
                    <option key={b} value={b}>{b}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Year</label>
                <select
                  value={formData.academicYear}
                  onChange={(e) => setFormData({ ...formData, academicYear: e.target.value })}
                  className="input-field"
                  data-testid="edit-year-select"
                >
                  <option value="">Select year</option>
                  {academicOptions.academic_years.map((y) => (
                    <option key={y} value={y}>{y}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="btn-primary"
                data-testid="save-profile-btn"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => setEditing(false)}
                className="btn-secondary"
                data-testid="cancel-edit-btn"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="w-full btn-secondary mb-4 flex items-center justify-center gap-2"
            data-testid="edit-profile-btn"
          >
            <GraduationCap className="w-5 h-5" />
            Edit Academic Info
          </button>
        )}

        <button
          onClick={onLogout}
          className="w-full btn-secondary flex items-center justify-center gap-2 text-red-600 border-red-200 hover:bg-red-50"
          data-testid="profile-logout-btn"
        >
          <LogOut className="w-5 h-5" />
          Logout
        </button>
      </div>
    </div>
  );
};

// Main App Component
function App() {
  const auth = useAuth();
  const [view, setView] = useState('rides'); // rides, myRides, requests, post, history, profile, stats
  const [rides, setRides] = useState([]);
  const [myRides, setMyRides] = useState([]);
  const [myRequests, setMyRequests] = useState([]);
  const [history, setHistory] = useState([]);
  const [pickupPoints, setPickupPoints] = useState([]);
  const [eventTags, setEventTags] = useState([]);
  const [academicOptions, setAcademicOptions] = useState({ branches: [], academic_years: [] });
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);
  
  // Rating modal state
  const [ratingModal, setRatingModal] = useState({
    isOpen: false,
    rideId: null,
    userToRate: null
  });

  // Fetch pickup points
  const fetchPickupPoints = useCallback(async () => {
    try {
      const response = await api.get('/api/pickup-points');
      setPickupPoints(response.data.pickup_points);
    } catch (err) {
      console.error('Failed to fetch pickup points:', err);
    }
  }, []);

  // Fetch event tags
  const fetchEventTags = useCallback(async () => {
    try {
      const response = await api.get('/api/event-tags');
      setEventTags(response.data.event_tags);
    } catch (err) {
      console.error('Failed to fetch event tags:', err);
    }
  }, []);

  // Fetch academic options
  const fetchAcademicOptions = useCallback(async () => {
    try {
      const response = await api.get('/api/academic-options');
      setAcademicOptions(response.data);
    } catch (err) {
      console.error('Failed to fetch academic options:', err);
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
      if (filters.eventTag) params.append('event_tag', filters.eventTag);
      if (filters.branch) params.append('branch', filters.branch);
      if (filters.academicYear) params.append('academic_year', filters.academicYear);
      
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

  // Fetch ride history
  const fetchHistory = useCallback(async () => {
    try {
      const endpoint = auth.user?.role === 'driver' ? '/api/history/driver' : '/api/history/rider';
      const response = await api.get(endpoint);
      setHistory(response.data.history);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  }, [auth.user?.role]);

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

  // Submit rating
  const submitRating = async (ratingData) => {
    try {
      await api.post('/api/ratings', ratingData);
      showNotification('Rating submitted successfully!');
      fetchMyRequests();
      fetchMyRides();
      auth.fetchUserInfo();
    } catch (err) {
      throw err;
    }
  };

  // Confirm safe completion
  const confirmSafeCompletion = async (rideId) => {
    try {
      await api.post('/api/safe-completion', { ride_id: rideId });
      showNotification('Safe arrival confirmed!');
      fetchMyRequests();
    } catch (err) {
      showNotification(err.response?.data?.detail || 'Failed to confirm', 'error');
    }
  };

  // Update ride status
  const updateRideStatus = async (rideId, status) => {
    try {
      await api.patch(`/api/rides/${rideId}/status?status=${status}`);
      showNotification(`Ride marked as ${status}!`);
      fetchMyRides();
    } catch (err) {
      showNotification(err.response?.data?.detail || 'Failed to update status', 'error');
    }
  };

  // Update profile
  const updateProfile = async (profileData) => {
    try {
      await api.patch('/api/auth/profile', {
        branch: profileData.branch || null,
        academic_year: profileData.academicYear || null
      });
      showNotification('Profile updated!');
      auth.fetchUserInfo();
    } catch (err) {
      showNotification(err.response?.data?.detail || 'Failed to update profile', 'error');
    }
  };

  // Open rating modal
  const openRatingModal = (rideId, userToRate) => {
    setRatingModal({
      isOpen: true,
      rideId,
      userToRate
    });
  };

  // Auth handlers
  const handleLogin = async (email, password, name, role, branch, academicYear, isSignup = false) => {
    if (isSignup) {
      await auth.signup(email, password, name, role, branch, academicYear);
    } else {
      await auth.login(email, password);
    }
  };

  // Initial data fetch
  useEffect(() => {
    if (auth.user) {
      fetchPickupPoints();
      fetchEventTags();
      fetchAcademicOptions();
      fetchRides();
      if (auth.user.role === 'driver') {
        fetchMyRides();
      } else {
        fetchMyRequests();
      }
    }
  }, [auth.user, fetchPickupPoints, fetchEventTags, fetchAcademicOptions, fetchRides, fetchMyRides, fetchMyRequests]);

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
            <button
              onClick={() => { setView('profile'); auth.fetchUserInfo(); }}
              className="flex items-center gap-2 hover:bg-gray-100 p-2 rounded-lg transition-colors"
              data-testid="profile-btn"
            >
              <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                <User className="w-4 h-4 text-blue-600" />
              </div>
              <div className="hidden sm:block text-left">
                <p className="text-sm font-medium text-gray-900">{auth.user.name}</p>
                <p className="text-xs text-gray-500 capitalize">{auth.user.role}</p>
              </div>
            </button>
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

      {/* Rating Modal */}
      <RatingModal
        isOpen={ratingModal.isOpen}
        onClose={() => setRatingModal({ isOpen: false, rideId: null, userToRate: null })}
        rideId={ratingModal.rideId}
        userToRate={ratingModal.userToRate}
        onSubmit={submitRating}
      />

      {/* Navigation */}
      <nav className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-4">
          <div className="flex gap-1 overflow-x-auto">
            <button
              onClick={() => { setView('rides'); fetchRides(); }}
              className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
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
                  className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
                    view === 'myRides' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                  data-testid="nav-my-rides"
                >
                  <Car className="w-4 h-4 inline mr-2" />
                  My Rides
                </button>
                <button
                  onClick={() => setView('post')}
                  className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
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
                className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
                  view === 'requests' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
                data-testid="nav-my-requests"
              >
                <Calendar className="w-4 h-4 inline mr-2" />
                My Requests
              </button>
            )}

            <button
              onClick={() => { setView('stats'); }}
              className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
                view === 'stats' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              data-testid="nav-stats"
            >
              <BarChart3 className="w-4 h-4 inline mr-2" />
              Insights
            </button>

            <button
              onClick={() => { setView('history'); fetchHistory(); }}
              className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
                view === 'history' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              data-testid="nav-history"
            >
              <History className="w-4 h-4 inline mr-2" />
              History
            </button>

            <button
              onClick={() => { setView('profile'); auth.fetchUserInfo(); }}
              className={`px-4 py-3 font-medium transition-colors border-b-2 whitespace-nowrap ${
                view === 'profile' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              data-testid="nav-profile"
            >
              <User className="w-4 h-4 inline mr-2" />
              Profile
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-6">
        {/* Find Rides View */}
        {view === 'rides' && (
          <div>
            <RideSearch 
              onSearch={fetchRides} 
              pickupPoints={pickupPoints}
              eventTags={eventTags}
              academicOptions={academicOptions}
            />
            
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
                    onUpdateStatus={updateRideStatus}
                    onRate={openRatingModal}
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
                  <RequestCard
                    key={request.id}
                    request={request}
                    onRate={openRatingModal}
                    onConfirmSafe={confirmSafeCompletion}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Post Ride View */}
        {view === 'post' && auth.user.role === 'driver' && (
          <PostRideForm
            pickupPoints={pickupPoints}
            eventTags={eventTags}
            onSubmit={postRide}
            onCancel={() => setView('myRides')}
          />
        )}

        {/* Statistics/Insights View */}
        {view === 'stats' && (
          <StatisticsDashboard user={auth.user} />
        )}

        {/* History View */}
        {view === 'history' && (
          <div>
            <h2 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-2">
              <History className="w-6 h-6 text-blue-600" />
              Ride History
            </h2>
            
            {history.length === 0 ? (
              <div className="card text-center py-12">
                <History className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No ride history yet</h3>
                <p className="text-gray-500">Your completed and cancelled rides will appear here</p>
              </div>
            ) : (
              <div className="space-y-4">
                {history.map((ride) => (
                  <HistoryCard key={ride.id} ride={ride} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Profile View */}
        {view === 'profile' && (
          <div className="max-w-md mx-auto">
            <ProfileCard 
              user={auth.user} 
              onLogout={auth.logout}
              onUpdateProfile={updateProfile}
            />
          </div>
        )}
      </main>
    </div>
  );
}

// Driver Ride Card with request management
const DriverRideCard = ({ ride, onAccept, onReject, onUpdateStatus, onRate }) => {
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
  const urgentCount = requests.filter(r => r.isUrgent && r.status === 'pending').length;
  const hasPendingRatings = ride.pendingRatings && ride.pendingRatings.length > 0;

  return (
    <div className="card" data-testid={`driver-ride-card-${ride.id}`}>
      <div className="flex flex-wrap gap-2 mb-3">
        {ride.eventTag && <EventTagBadge eventTag={ride.eventTag} />}
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
        {ride.distanceKm && (
          <div className="flex items-center gap-2 text-gray-600">
            <MapPin className="w-4 h-4" />
            <span>{ride.distanceKm} km</span>
          </div>
        )}
      </div>

      {/* Status Actions */}
      {ride.status === 'posted' && (
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => onUpdateStatus(ride.id, 'in_progress')}
            className="btn-primary text-sm"
            data-testid="start-ride-btn"
          >
            Start Ride
          </button>
          <button
            onClick={() => onUpdateStatus(ride.id, 'cancelled')}
            className="btn-secondary text-sm"
            data-testid="cancel-ride-btn"
          >
            Cancel
          </button>
        </div>
      )}

      {ride.status === 'in_progress' && (
        <div className="mb-4">
          <button
            onClick={() => onUpdateStatus(ride.id, 'completed')}
            className="btn-primary text-sm bg-green-600 hover:bg-green-700"
            data-testid="complete-ride-btn"
          >
            <Check className="w-4 h-4 inline mr-1" />
            Mark as Completed
          </button>
        </div>
      )}

      {/* Pending Ratings */}
      {hasPendingRatings && (
        <div className="mb-4 p-3 bg-yellow-50 rounded-lg border border-yellow-100">
          <p className="text-sm font-medium text-yellow-800 mb-2 flex items-center gap-2">
            <Star className="w-4 h-4" />
            Rate your riders
          </p>
          <div className="flex flex-wrap gap-2">
            {ride.pendingRatings.map((rider) => (
              <button
                key={rider.userId}
                onClick={() => onRate(ride.id, rider)}
                className="text-sm bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full hover:bg-yellow-200 transition-colors"
                data-testid={`rate-rider-${rider.userId}`}
              >
                Rate {rider.userName}
              </button>
            ))}
          </div>
        </div>
      )}

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
