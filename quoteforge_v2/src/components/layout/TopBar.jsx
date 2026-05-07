import { useNavigate } from 'react-router-dom';
import { Search, Bell, ChevronDown, LogOut, Shield, User } from 'lucide-react';
import { useAuth } from '@context/AuthContext';
import { useState } from 'react';

export default function TopBar({ title, subtitle }) {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="px-8 h-[72px] flex items-center justify-between border-b border-gray-200 bg-white sticky top-0 z-40">
      {/* Page Title */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 tracking-tight">{title}</h1>
        <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {/* Search */}
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search..."
            className="input-field pl-10 pr-4 h-[38px] w-[220px] bg-gray-50 focus:bg-white"
          />
        </div>

        {/* Notifications */}
        <button className="relative w-[38px] h-[38px] rounded-xl border border-gray-200 bg-white cursor-pointer flex items-center justify-center hover:bg-gray-50 transition-colors">
          <Bell size={18} className="text-gray-500" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500 border-2 border-white" />
        </button>

        {/* Role badge */}
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold ${
          isAdmin ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
        }`}>
          {isAdmin ? <Shield size={12} /> : <User size={12} />}
          {isAdmin ? 'Admin' : 'User'}
        </span>

        {/* User Dropdown */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors"
          >
            <div className="w-[30px] h-[30px] rounded-lg bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center text-white text-sm font-semibold">
              {user?.avatar || 'U'}
            </div>
            <span className="text-sm font-semibold text-gray-700">{user?.name?.split(' ')[0]}</span>
            <ChevronDown size={14} className="text-gray-400" />
          </button>

          {dropdownOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setDropdownOpen(false)} />
              <div className="absolute right-0 top-full mt-2 w-[220px] bg-white rounded-xl border border-gray-200 shadow-xl py-2 z-50">
                <div className="px-4 py-2.5 border-b border-gray-100">
                  <div className="text-sm font-semibold text-gray-900">{user?.name}</div>
                  <div className="text-xs text-gray-500">{user?.email}</div>
                </div>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2.5 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
                >
                  <LogOut size={16} />
                  Sign Out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
