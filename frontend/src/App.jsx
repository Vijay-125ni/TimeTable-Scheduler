import React, { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, Outlet, Navigate } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';

const Dashboard = React.lazy(() => import('./components/Admin/Dashboard'));
const DepartmentManager = React.lazy(() => import('./components/Admin/DepartmentManager'));
const ClassManager = React.lazy(() => import('./components/Admin/ClassManager'));
const RoomManager = React.lazy(() => import('./components/Admin/RoomManager'));
const SubjectManager = React.lazy(() => import('./components/Admin/SubjectManager'));
const FacultyManager = React.lazy(() => import('./components/Admin/FacultyManager'));
const BatchManager = React.lazy(() => import('./components/Admin/BatchManager'));
const FacultyMapping = React.lazy(() => import('./components/Admin/FacultyMapping'));
const TimetableGenerator = React.lazy(() => import('./components/Timetable/TimetableGenerator'));
const TimetableView = React.lazy(() => import('./components/Timetable/TimetableView'));
const Settings = React.lazy(() => import('./components/Admin/Settings'));
const Login = React.lazy(() => import('./components/Login'));
const UploadPage = React.lazy(() => import('./components/KnowledgeIngestion/UploadPage'));
const ProcessingPage = React.lazy(() => import('./components/KnowledgeIngestion/ProcessingPage'));
const DuplicateReview = React.lazy(() => import('./components/KnowledgeIngestion/DuplicateReview'));
const UploadHistory = React.lazy(() => import('./components/KnowledgeIngestion/UploadHistory'));
const AuditLogs = React.lazy(() => import('./components/KnowledgeIngestion/AuditLogs'));
const LearningRules = React.lazy(() => import('./components/KnowledgeIngestion/LearningRules'));
import Sidebar from './components/Layout/Sidebar';
import { ToastProvider } from './context/ToastContext';

// ProtectedRoute checks if user is logged in before rendering children
const ProtectedRoute = ({ children }) => {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

// LoginRoute redirects to dashboard if user is already logged in
const LoginRoute = () => {
  if (isAuthenticated()) {
    return <Navigate to="/" replace />;
  }
  return <Login />;
};

function App() {
  const MainLayout = () => {
    const location = useLocation();
    const isWideView = location.pathname.includes('/view');
    const maxWidthClass = isWideView ? 'max-w-full' : 'max-w-6xl mx-auto';
    const paddingClass = isWideView ? 'p-2 sm:p-4' : 'p-4 sm:p-6 md:p-8';

    return (
      <div className="flex h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
        <Sidebar />
        <div className={`flex-1 main-content ${paddingClass} overflow-y-auto h-full relative`}>
          <div key={location.pathname} className={`${maxWidthClass} animate-page`}>
            <Outlet />
          </div>
        </div>
      </div>
    );
  };

  return (
    <ToastProvider>
      <Router>
        
        <Suspense fallback={
            <div className="flex flex-col items-center justify-center h-screen space-y-4 bg-slate-50">
                <div className="w-12 h-12 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
                <div className="text-xl font-medium text-slate-500">Loading Application...</div>
            </div>
        }>
          <Routes>
            <Route path="/login" element={<LoginRoute />} />

            <Route path="/" element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }>
              <Route index element={<Dashboard />} />
              <Route path="departments" element={<DepartmentManager />} />
              <Route path="batches" element={<BatchManager />} />
              <Route path="classes" element={<ClassManager />} />
              <Route path="rooms" element={<RoomManager />} />
              <Route path="subjects" element={<SubjectManager />} />
              <Route path="faculty" element={<FacultyManager />} />
              <Route path="mapping" element={<FacultyMapping />} />
              <Route path="generate" element={<TimetableGenerator />} />

              {/* Knowledge Ingestion Module */}
              <Route path="knowledge/upload" element={<UploadPage />} />
              <Route path="knowledge/processing/:sessionId" element={<ProcessingPage />} />
              <Route path="knowledge/review/:sessionId" element={<DuplicateReview />} />
              <Route path="knowledge/history" element={<UploadHistory />} />
              <Route path="knowledge/audit-logs" element={<AuditLogs />} />
              <Route path="knowledge/learning-rules" element={<LearningRules />} />
              
              <Route path="view" element={<TimetableView />} />
              <Route path="settings" element={<Settings />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Router>
    </ToastProvider>
  );
}

export default App;
