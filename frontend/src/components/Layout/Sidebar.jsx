import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { isAdmin, removeToken } from '../../utils/auth';
import {
    Menu,
    LayoutDashboard,
    Building2,
    Layers,
    Users,
    BookOpen,
    DoorOpen,
    GitMerge,
    Cpu,
    Table,
    Settings,
    LogOut,
    GraduationCap,
    Brain,
    Upload,
    History,
    ClipboardList,
    BookMarked
} from 'lucide-react';

const Icons = {
    Dashboard: LayoutDashboard,
    Departments: Building2,
    Batches: Layers,
    Classes: GraduationCap,
    Rooms: DoorOpen,
    Subjects: BookOpen,
    Faculty: Users,
    Mapping: GitMerge,
    Generate: Cpu,
    Timetables: Table,
    Settings: Settings,
    Logout: LogOut
};

export default function Sidebar() {
    const location = useLocation();
    const navigate = useNavigate();
    const [isExpanded, setIsExpanded] = useState(false);
    const admin = isAdmin();
    
    const isActive = (path) => location.pathname === path;

    const handleLogout = () => {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
    };

    const NavItem = ({ to, label, icon: Icon }) => (
        <Link
            to={to}
            className={`flex items-center h-12 px-4 relative group transition-all duration-1000 ease ${isActive(to)
                    ? 'bg-primary-600 text-white shadow-lg'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`}
        >
            <Icon size={22} className="shrink-0" />
            <span className={`ml-4 font-bold text-sm whitespace-nowrap overflow-hidden transition-all duration-1000 ease ${isExpanded ? 'max-w-[200px] opacity-100' : 'max-w-0 opacity-0'
                }`}>
                {label}
            </span>

            {!isExpanded && (
                <div className="absolute left-16 bg-slate-800 text-white px-3 py-1.5 rounded-md text-xs font-bold opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-300 ease whitespace-nowrap shadow-xl border border-slate-700 z-50">
                    {label}
                </div>
            )}
        </Link>
    );

    return (
        <div
            className={`h-full bg-slate-900 flex flex-col z-[100] border-r border-slate-800/50 transition-all duration-1000 ease ${isExpanded ? 'w-64' : 'w-16'
                }`}
            onMouseEnter={() => setIsExpanded(true)}
            onMouseLeave={() => setIsExpanded(false)}
        >
            <div className="h-20 flex items-center px-4 border-b border-slate-800/50">
                <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center shrink-0 shadow-lg shadow-primary-500/20">
                    <Menu size={20} className="text-white" />
                </div>
                <h1 className={`ml-4 text-sm font-black text-white uppercase tracking-tight whitespace-nowrap overflow-hidden transition-all duration-1000 ease ${isExpanded ? 'max-w-[200px] opacity-100' : 'max-w-0 opacity-0'
                    }`}>
                    Time Table Scheduler
                </h1>
            </div>

            <nav className="flex-1 overflow-y-auto py-6 scrollbar-hide space-y-1">
                <NavItem to="/" label="Dashboard" icon={Icons.Dashboard} />

                {admin && (
                    <>
                        <div className="h-px bg-slate-800 my-4 mx-4" />
                        <NavItem to="/departments" label="Departments" icon={Icons.Departments} />
                        <NavItem to="/batches" label="Batches" icon={Icons.Batches} />
                        <NavItem to="/classes" label="Classes" icon={Icons.Classes} />
                        <NavItem to="/rooms" label="Rooms" icon={Icons.Rooms} />
                        <NavItem to="/subjects" label="Subjects" icon={Icons.Subjects} />
                        <NavItem to="/faculty" label="Faculty" icon={Icons.Faculty} />
                        <NavItem to="/mapping" label="Mapping" icon={Icons.Mapping} />
                        
                        <div className="h-px bg-slate-800 my-4 mx-4" />
                        <NavItem to="/generate" label="Generate" icon={Icons.Generate} />

                        <div className="h-px bg-slate-800 my-4 mx-4" />
                        {/* Knowledge Ingestion */}
                        <div className={`px-4 py-1 overflow-hidden transition-all duration-1000 ${isExpanded ? 'opacity-100' : 'opacity-0 h-0'}`}>
                            <span className="text-xs font-black text-slate-600 uppercase tracking-widest">Knowledge AI</span>
                        </div>
                        <NavItem to="/knowledge/upload" label="Upload Docs" icon={Upload} />
                        <NavItem to="/knowledge/history" label="Upload History" icon={History} />
                        <NavItem to="/knowledge/audit-logs" label="Audit Logs" icon={ClipboardList} />
                        <NavItem to="/knowledge/learning-rules" label="Learning Rules" icon={BookMarked} />
                    </>
                )}
                
                <NavItem to="/view" label="Timetables" icon={Icons.Timetables} />
                <NavItem to="/settings" label="Settings" icon={Icons.Settings} />
            </nav>

            <div className="border-t border-slate-800/50 p-2">
                <button
                    onClick={handleLogout}
                    className="flex items-center w-full h-12 px-4 rounded-xl text-slate-400 hover:bg-red-500/10 hover:text-red-400 group transition-all duration-300 relative cursor-pointer"
                >
                    <Icons.Logout size={22} className="shrink-0" />
                    <span className={`ml-4 font-bold text-sm whitespace-nowrap overflow-hidden transition-all duration-1000 ease ${isExpanded ? 'max-w-[200px] opacity-100' : 'max-w-0 opacity-0'
                        }`}>
                        Logout
                    </span>
                    {!isExpanded && (
                        <div className="absolute left-16 bg-red-600 text-white px-3 py-1.5 rounded-md text-xs font-bold opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-300 ease whitespace-nowrap shadow-xl z-50">
                            Logout
                        </div>
                    )}
                </button>
            </div>
        </div>
    );
}
