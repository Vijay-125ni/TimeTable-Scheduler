import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authAPI } from '../services/api';
import { setToken, setUser, firebaseEmailLogin, firebaseEmailRegister, firebaseGoogleLogin } from '../utils/auth';
import { useToast } from '../context/ToastContext';
import {
  Calendar,
  Lock,
  User,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  GraduationCap,
  Clock,
  Cpu,
  BookOpen,
  Network
} from 'lucide-react';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const navigate = useNavigate();
  const { showToast } = useToast();

  const cardRef = useRef(null);
  const [tiltStyle, setTiltStyle] = useState({});

  // 3D Parallax Tilt Effect on Mouse Move
  const handleMouseMove = (e) => {
    if (!cardRef.current) return;
    const card = cardRef.current;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;

    // Constrain rotation to maximum of 4 degrees for subtle premium feel
    const rotateX = -(y / (rect.height / 2)) * 4;
    const rotateY = (x / (rect.width / 2)) * 4;

    setTiltStyle({
      transform: `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`,
      transition: 'transform 0.08s ease-out, box-shadow 0.3s ease'
    });
  };

  const handleMouseLeave = () => {
    setTiltStyle({
      transform: 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0px)',
      transition: 'transform 0.6s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s ease'
    });
  };

  const handleLogin = async (e) => {
    if (e) e.preventDefault();

    if (isSignUp) {
      if (!username.trim() || !email.trim() || !password.trim() || !fullName.trim()) {
        setErrorMsg('Please fill in all fields.');
        return;
      }
      setErrorMsg('');
      setIsLoading(true);

      try {
        // 1. Register via Firebase Auth
        const firebaseUser = await firebaseEmailRegister(email.trim(), password.trim(), fullName.trim());
        
        // 2. Call backend /api/auth/register to save to MongoDB and create database tenant
        await authAPI.register({
          uid: firebaseUser.uid,
          username: username.trim(),
          email: email.trim(),
          full_name: fullName.trim(),
          role: 'admin'
        });

        // 3. Fetch latest profile from backend to get tenant details and role
        try {
          const userRes = await authAPI.getCurrentUser();
          setUser(userRes.data);
        } catch (meErr) {
          console.warn("Could not sync backend profile, fallback to local object", meErr);
        }

        showToast('Successfully registered new admin workspace!', 'success');
        navigate('/');
        return;
      } catch (err) {
        setErrorMsg(err.response?.data?.detail || err.message || 'Registration failed.');
        setIsLoading(false);
        return;
      }
    }

    if (!username.trim() || !password.trim()) {
      setErrorMsg('Please enter both username and password.');
      return;
    }

    setErrorMsg('');
    setIsLoading(true);

    try {
      // 1. Try Firebase Authentication first
      const firebaseUser = await firebaseEmailLogin(username.trim(), password.trim());
      
      // Fetch profile from backend to get true role and tenant_db_name
      try {
        const userRes = await authAPI.getCurrentUser();
        setUser(userRes.data);
      } catch (meErr) {
        // Fallback to local inference if backend fetch fails
        const isAdminUser = firebaseUser.email?.toLowerCase().includes('admin');
        setUser({
          uid: firebaseUser.uid,
          username: firebaseUser.displayName || firebaseUser.email.split('@')[0],
          full_name: firebaseUser.displayName || firebaseUser.email.split('@')[0],
          email: firebaseUser.email,
          role: isAdminUser ? 'admin' : 'faculty',
          is_admin: isAdminUser,
        });
      }

      showToast('Successfully logged in!', 'success');
      navigate('/');
      return;
    } catch (firebaseErr) {
      console.warn('Firebase auth failed, trying backend API...', firebaseErr.message);
    }

    try {
      // 2. Fallback: Try backend API login
      const response = await authAPI.login(username, password);
      const data = response.data;
      if (data && data.access_token) {
        setToken(data.access_token);

        try {
          const userRes = await authAPI.getCurrentUser();
          setUser(userRes.data);
        } catch (profileErr) {
          setUser({
            username: username,
            full_name: username.charAt(0).toUpperCase() + username.slice(1),
            role: username.toLowerCase().includes('admin') ? 'admin' : 'faculty',
            is_admin: username.toLowerCase().includes('admin')
          });
        }

        showToast('Successfully logged in!', 'success');
        navigate('/');
        return;
      }
    } catch (apiErr) {
      console.warn('Backend API auth failed, trying demo credentials...', apiErr.message);
    }

    // 3. Fallback: Mock demo credentials
    const normalizedUser = username.trim().toLowerCase();
    const normalizedPass = password.trim();

    if (normalizedUser === 'admin' && normalizedPass === 'admin123') {
      setToken('mock-admin-token-12345');
      setUser({
        username: 'admin',
        full_name: 'Administrator',
        role: 'admin',
        is_admin: true,
        tenant_db_name: 'timetable_scheduler'
      });
      showToast('Demo Admin Logged In', 'success');
      navigate('/');
    } else if (normalizedUser === 'faculty' && normalizedPass === 'faculty123') {
      setToken('mock-faculty-token-54321');
      setUser({
        username: 'faculty',
        full_name: 'Dr. Jane Smith (Faculty)',
        role: 'faculty',
        is_admin: false,
        tenant_db_name: 'timetable_scheduler'
      });
      showToast('Demo Faculty Logged In', 'success');
      navigate('/');
    } else {
      setErrorMsg('Invalid credentials. Check your email/password or use demo access below.');
    }

    setIsLoading(false);
  };

  const handleGoogleLogin = async () => {
    setErrorMsg('');
    setIsLoading(true);
    try {
      // 1. Authenticate with Google via Firebase Popup
      const firebaseUser = await firebaseGoogleLogin();
      
      // 2. If signing up, register in central DB as Admin
      if (isSignUp) {
        try {
          await authAPI.register({
            uid: firebaseUser.uid,
            username: firebaseUser.email.split('@')[0],
            email: firebaseUser.email,
            full_name: firebaseUser.displayName || firebaseUser.email.split('@')[0],
            role: 'admin'
          });
        } catch (regErr) {
          // If already registered, it's fine, we proceed to login/fetch profile
          if (regErr.response?.data?.detail !== "Username or email already registered") {
            throw regErr;
          }
        }
      }

      // 3. Fetch latest profile from backend to get tenant info and role
      try {
        const userRes = await authAPI.getCurrentUser();
        setUser(userRes.data);
      } catch (meErr) {
        console.warn("Could not sync backend profile, falling back to local user details", meErr);
        if (isSignUp) {
          setUser({
            uid: firebaseUser.uid,
            username: firebaseUser.email.split('@')[0],
            full_name: firebaseUser.displayName || '',
            email: firebaseUser.email,
            role: 'admin',
            is_admin: true,
          });
        }
      }

      showToast(isSignUp ? 'Successfully signed up and logged in with Google!' : 'Successfully logged in with Google!', 'success');
      navigate('/');
    } catch (err) {
      console.error(err);
      setErrorMsg(err.message || 'Google authentication failed.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemoFill = (role) => {
    setErrorMsg('');
    if (role === 'admin') {
      setUsername('admin');
      setPassword('admin123');
    } else {
      setUsername('faculty');
      setPassword('faculty123');
    }
    
    // Automatically submit after filling demo credentials for super smooth interaction
    // Scheduling this here ensures it only runs on explicit click of the demo buttons,
    // avoiding issues with browser autofills triggering automatic logins on click anywhere.
    setTimeout(() => {
      handleLogin();
    }, 400);
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 md:p-8 relative overflow-hidden select-none bg-bg-primary font-sans">
      
      {/* BACKGROUND DECORATIONS */}
      {/* Soft mesh background */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(247,249,252,0.85),rgba(247,249,252,0.85)),radial-gradient(at_top_left,rgba(79,124,255,0.09),transparent_60%),radial-gradient(at_bottom_right,rgba(108,92,255,0.06),transparent_60%)] pointer-events-none" />

      {/* Very soft blue radial gradients and moving blobs */}
      <div className="absolute top-[-15%] left-[-10%] w-[50vw] h-[50vw] max-w-[600px] max-h-[600px] rounded-full bg-accent-blue/8 blur-[100px] pointer-events-none animate-blob-drift" />
      <div className="absolute bottom-[-15%] right-[-10%] w-[55vw] h-[55vw] max-w-[700px] max-h-[700px] rounded-full bg-grad-end/6 blur-[120px] pointer-events-none animate-blob-drift-reverse" />
      
      {/* Floating glass shapes */}
      <div className="absolute top-[18%] right-[12%] w-[220px] h-[110px] rounded-full bg-white/10 border border-white/20 backdrop-blur-[10px] animate-float-slow pointer-events-none select-none hidden lg:block opacity-40 shadow-[0_10px_30px_rgba(0,0,0,0.01)]" />
      <div className="absolute bottom-[22%] left-[10%] w-[130px] h-[130px] rounded-[38px] bg-white/8 border border-white/15 backdrop-blur-[8px] animate-float-slower rotate-[15deg] pointer-events-none select-none hidden lg:block opacity-35 shadow-[0_10px_30px_rgba(0,0,0,0.01)]" />
      
      {/* Tiny glowing particles */}
      <div className="absolute top-[30%] left-[25%] w-2 h-2 rounded-full bg-accent-blue/30 blur-[1px] animate-float-slow" style={{ animationDelay: '1s' }} />
      <div className="absolute top-[75%] left-[40%] w-1.5 h-1.5 rounded-full bg-grad-end/25 blur-[1px] animate-float-slower" style={{ animationDelay: '3s' }} />
      <div className="absolute top-[20%] right-[35%] w-2.5 h-2.5 rounded-full bg-accent-blue/20 blur-[1.5px] animate-float-slow" style={{ animationDelay: '0.5s' }} />
      <div className="absolute bottom-[35%] right-[22%] w-1.5 h-1.5 rounded-full bg-grad-end/30 blur-[0.8px] animate-float-slower" style={{ animationDelay: '2.2s' }} />

      {/* Subtle floating academic decoration icons */}
      <div className="absolute top-[12%] left-[15%] text-accent-blue/15 animate-float-slow pointer-events-none select-none" style={{ animationDelay: '0s' }}>
        <GraduationCap size={44} strokeWidth={1.2} />
      </div>
      <div className="absolute top-[15%] right-[20%] text-grad-end/15 animate-float-slower pointer-events-none select-none" style={{ animationDelay: '1.5s' }}>
        <Clock size={36} strokeWidth={1.2} />
      </div>
      <div className="absolute bottom-[28%] left-[18%] text-accent-blue/15 animate-float-slower pointer-events-none select-none" style={{ animationDelay: '2.5s' }}>
        <Cpu size={40} strokeWidth={1.2} />
      </div>
      <div className="absolute bottom-[16%] right-[15%] text-grad-end/15 animate-float-slow pointer-events-none select-none" style={{ animationDelay: '0.8s' }}>
        <BookOpen size={42} strokeWidth={1.2} />
      </div>
      <div className="absolute top-[48%] left-[6%] text-accent-blue/10 animate-float-slower pointer-events-none select-none" style={{ animationDelay: '3.2s' }}>
        <Calendar size={38} strokeWidth={1.2} />
      </div>
      <div className="absolute top-[55%] right-[8%] text-grad-end/10 animate-float-slow pointer-events-none select-none" style={{ animationDelay: '2s' }}>
        <Network size={40} strokeWidth={1.2} />
      </div>

      {/* LOGIN CARD WRAPPER */}
      <div 
        ref={cardRef}
        style={tiltStyle}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className="relative w-full max-w-[480px] bg-white/78 backdrop-blur-[30px] rounded-[28px] border border-white/60 p-8 md:p-12 shadow-premium hover:shadow-premium-hover transition-all duration-300 z-10 animate-fade-in-up"
      >
        
        {/* LOGO & BRAND HEADER */}
        <div className="text-center mb-10 flex flex-col items-center select-none">
          <div className="relative mb-5 flex items-center justify-center">
            {/* Soft glow behind the logo */}
            <div className="absolute -inset-4 bg-accent-blue/20 rounded-full blur-xl animate-pulse" />
            {/* Logo container */}
            <div className="relative w-[72px] h-[72px] bg-gradient-to-tr from-accent-blue to-grad-end rounded-2xl flex items-center justify-center shadow-lg shadow-accent-blue/20 text-white animate-float-slow">
              <Calendar size={34} className="text-white" strokeWidth={2.2} />
            </div>
          </div>
          <h2 className="text-[34px] font-extrabold text-text-primary tracking-tight leading-none font-sans">
            {isSignUp ? 'Create Workspace' : 'AI Timetable Scheduler'}
          </h2>
          <p className="text-[14px] font-medium text-text-secondary mt-2.5 max-w-[300px] leading-relaxed">
            {isSignUp ? 'Sign up as Admin to manage your isolated academic schedules' : 'Generate Academic Schedules using Artificial Intelligence'}
          </p>
        </div>

        {/* ERROR DISPLAY */}
        {errorMsg && (
          <div className="mb-6 p-4 bg-red-50/60 backdrop-blur-md border border-red-200/40 rounded-2xl text-[13px] font-semibold text-red-600 flex items-start gap-3 animate-headshake">
            <AlertCircle size={18} className="shrink-0 text-red-500 mt-0.5" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* FORM */}
        <form onSubmit={handleLogin} className="space-y-5">
          
          {/* FULL NAME INPUT (SIGN UP ONLY) */}
          {isSignUp && (
            <div className="relative flex items-center h-[58px] bg-[#F8FAFC] border border-transparent rounded-[16px] hover:border-accent-blue/30 focus-within:border-accent-blue focus-within:ring-[3px] focus-within:ring-accent-blue/15 transition-all duration-300">
              <span className="absolute left-4 text-text-secondary/50 transition-colors pointer-events-none">
                <User size={18} />
              </span>
              <input
                id="fullName"
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder=" "
                className="peer w-full h-full pl-12 pr-4 pt-4 bg-transparent outline-none text-[15px] font-semibold text-text-primary"
              />
              <label
                htmlFor="fullName"
                className="absolute left-12 top-1/2 -translate-y-1/2 text-[14px] font-semibold text-text-secondary/50 pointer-events-none transition-all duration-200 peer-focus:text-[10px] peer-focus:translate-y-[-16px] peer-focus:text-accent-blue peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:translate-y-[-16px]"
              >
                Full Name
              </label>
            </div>
          )}

          {/* USERNAME INPUT */}
          <div className="relative flex items-center h-[58px] bg-[#F8FAFC] border border-transparent rounded-[16px] hover:border-accent-blue/30 focus-within:border-accent-blue focus-within:ring-[3px] focus-within:ring-accent-blue/15 transition-all duration-300">
            <span className="absolute left-4 text-text-secondary/50 transition-colors pointer-events-none">
              <User size={18} />
            </span>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder=" "
              className="peer w-full h-full pl-12 pr-4 pt-4 bg-transparent outline-none text-[15px] font-semibold text-text-primary"
            />
            <label
              htmlFor="username"
              className="absolute left-12 top-1/2 -translate-y-1/2 text-[14px] font-semibold text-text-secondary/50 pointer-events-none transition-all duration-200 peer-focus:text-[10px] peer-focus:translate-y-[-16px] peer-focus:text-accent-blue peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:translate-y-[-16px]"
            >
              {isSignUp ? 'Username' : 'Username or Email ID'}
            </label>
          </div>

          {/* EMAIL INPUT (SIGN UP ONLY) */}
          {isSignUp && (
            <div className="relative flex items-center h-[58px] bg-[#F8FAFC] border border-transparent rounded-[16px] hover:border-accent-blue/30 focus-within:border-accent-blue focus-within:ring-[3px] focus-within:ring-accent-blue/15 transition-all duration-300">
              <span className="absolute left-4 text-text-secondary/50 transition-colors pointer-events-none">
                <Mail size={18} />
              </span>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder=" "
                className="peer w-full h-full pl-12 pr-4 pt-4 bg-transparent outline-none text-[15px] font-semibold text-text-primary"
              />
              <label
                htmlFor="email"
                className="absolute left-12 top-1/2 -translate-y-1/2 text-[14px] font-semibold text-text-secondary/50 pointer-events-none transition-all duration-200 peer-focus:text-[10px] peer-focus:translate-y-[-16px] peer-focus:text-accent-blue peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:translate-y-[-16px]"
              >
                Email Address
              </label>
            </div>
          )}

          {/* PASSWORD INPUT */}
          <div className="relative flex items-center h-[58px] bg-[#F8FAFC] border border-transparent rounded-[16px] hover:border-accent-blue/30 focus-within:border-accent-blue focus-within:ring-[3px] focus-within:ring-accent-blue/15 transition-all duration-300">
            <span className="absolute left-4 text-text-secondary/50 transition-colors pointer-events-none">
              <Lock size={18} />
            </span>
            <input
              id="password"
              type={showPassword ? 'text' : 'password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder=" "
              className="peer w-full h-full pl-12 pr-14 pt-4 bg-transparent outline-none text-[15px] font-semibold text-text-primary"
            />
            <label
              htmlFor="password"
              className="absolute left-12 top-1/2 -translate-y-1/2 text-[14px] font-semibold text-text-secondary/50 pointer-events-none transition-all duration-200 peer-focus:text-[10px] peer-focus:translate-y-[-16px] peer-focus:text-accent-blue peer-[:not(:placeholder-shown)]:text-[10px] peer-[:not(:placeholder-shown)]:translate-y-[-16px]"
            >
              Password
            </label>
            {/* Eye Toggle Container */}
            <div className="absolute right-3.5 flex items-center justify-center">
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="p-1.5 bg-slate-200/40 hover:bg-slate-200/70 rounded-full text-text-secondary hover:text-text-primary transition-all duration-200 cursor-pointer"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* REMEMBER & FORGOT (SIGN IN ONLY) */}
          {!isSignUp && (
            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                className="text-[13px] ml-auto font-bold text-black hover:text-grad-end transition-colors cursor-pointer"
              >
                Forgot password?
              </button>
            </div>
          )}

          {/* SUBMIT BUTTON */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full h-[58px] relative group flex items-center justify-center bg-gradient-to-r from-accent-blue to-grad-end text-white font-bold rounded-[16px] text-[15px] transition-all duration-300 shadow-premium-glow hover:shadow-[0_15px_35px_rgba(79,124,255,0.35)] hover:-translate-y-0.5 active:scale-[0.98] disabled:opacity-75 disabled:pointer-events-none cursor-pointer"
          >
            {isLoading ? (
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <span className="flex items-center justify-center gap-2 tracking-wide">
                {isSignUp ? 'Sign Up' : 'Sign In'} 
                <ArrowRight size={18} className="group-hover:translate-x-1.5 transition-transform duration-300" />
              </span>
            )}
          </button>
        </form>

        {/* OR SEPARATOR */}
        <div className="flex items-center my-5">
          <div className="flex-grow border-t border-slate-200/50"></div>
          <span className="px-3 text-[11px] font-bold text-text-secondary/70 tracking-wider uppercase">Or connect with</span>
          <div className="flex-grow border-t border-slate-200/50"></div>
        </div>

        {/* GOOGLE SIGN IN BUTTON */}
        <button
          type="button"
          onClick={handleGoogleLogin}
          disabled={isLoading}
          className="w-full h-[58px] flex items-center justify-center gap-3 bg-white/70 hover:bg-white border border-slate-200 hover:border-slate-300/80 rounded-[16px] text-text-primary text-[15px] font-bold shadow-sm hover:shadow-md transition-all duration-300 active:scale-[0.98] disabled:opacity-70 disabled:pointer-events-none cursor-pointer group"
        >
          <svg className="w-5 h-5 shrink-0 group-hover:scale-110 transition-transform duration-300" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            />
          </svg>
          <span className="tracking-wide">
            {isSignUp ? 'Continue with Google' : 'Sign In with Google'}
          </span>
        </button>

        {/* TOGGLE MODE */}
        <div className="text-center pt-4">
          <button
            type="button"
            onClick={() => {
              setIsSignUp(!isSignUp);
              setErrorMsg('');
            }}
            className="text-[13px] font-bold text-accent-blue hover:text-grad-end transition-colors cursor-pointer"
          >
            {isSignUp ? 'Already have an account? Sign In' : "Sign Up Here"}
          </button>
        </div>

        {/* QUICK LOGIN ROLE CARDS (SIGN IN ONLY) */}
        {!isSignUp && (
          <div className="space-y-4 pt-8 border-t border-premium-border mt-8">
            <div className="flex items-center justify-center gap-1.5 text-[11px] font-bold text-text-secondary/70 tracking-widest uppercase">
              <Sparkles size={14} className="text-yellow-500" />
              <span>Quick Demo Access</span>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => handleDemoFill('admin')}
                className="group flex flex-col items-start p-4 rounded-2xl border border-premium-border bg-slate-50/40 hover:bg-white hover:border-accent-blue/40 hover:shadow-premium transition-all duration-300 text-left relative overflow-hidden cursor-pointer"
              >
                <div className="absolute top-0 right-0 w-[40px] h-[40px] bg-accent-blue/5 rounded-bl-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                <div className="flex items-center gap-2 mb-2 w-full">
                  <div className="p-1.5 bg-accent-blue/10 rounded-lg text-accent-blue group-hover:scale-110 transition-transform duration-300">
                    <ShieldCheck size={16} />
                  </div>
                  <span className="text-[13px] font-extrabold text-text-primary">Admin</span>
                  <span className="text-[9px] font-bold bg-accent-blue/10 text-accent-blue px-1.5 py-0.5 rounded-full ml-auto">
                    Demo
                  </span>
                </div>
                <p className="text-[11px] text-text-secondary font-medium leading-relaxed">
                  Full configuration and scheduling access.
                </p>
              </button>
              
              <button
                type="button"
                onClick={() => handleDemoFill('faculty')}
                className="group flex flex-col items-start p-4 rounded-2xl border border-premium-border bg-slate-50/40 hover:bg-white hover:border-grad-end/40 hover:shadow-premium transition-all duration-300 text-left relative overflow-hidden cursor-pointer"
              >
                <div className="absolute top-0 right-0 w-[40px] h-[40px] bg-grad-end/5 rounded-bl-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
                <div className="flex items-center gap-2 mb-2 w-full">
                  <div className="p-1.5 bg-grad-end/10 rounded-lg text-grad-end group-hover:scale-110 transition-transform duration-300">
                    <GraduationCap size={16} />
                  </div>
                  <span className="text-[13px] font-extrabold text-text-primary">Faculty</span>
                  <span className="text-[9px] font-bold bg-grad-end/10 text-grad-end px-1.5 py-0.5 rounded-full ml-auto">
                    Demo
                  </span>
                </div>
                <p className="text-[11px] text-text-secondary font-medium leading-relaxed">
                  View schedules and manage faculty slots.
                </p>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* FOOTER */}
      <div className="w-full max-w-[480px] flex items-center justify-between mt-6 text-[11px] font-bold text-text-secondary/50 px-4 select-none z-10">
        <span>© 2026 AI Timetable Scheduler</span>
        <div className="flex items-center gap-3">
          <a href="#" className="hover:text-text-primary transition-colors">Privacy Policy</a>
          <span className="w-1 h-1 bg-slate-300 rounded-full" />
          <a href="#" className="hover:text-text-primary transition-colors">Terms</a>
        </div>
      </div>

    </div>
  );
}
