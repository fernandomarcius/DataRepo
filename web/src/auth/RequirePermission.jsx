import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// Fallback order: if user can query, send to /; otherwise /reports is always accessible.
const fallbackFor = (user) => {
    if (user?.perms?.can_query) return '/';
    return '/reports';
};

const RequirePermission = ({ flag, redirectTo, children }) => {
    const { user, loading, hasPermission } = useAuth();
    if (loading) return null;
    if (!hasPermission(flag)) {
        return <Navigate to={redirectTo || fallbackFor(user)} replace />;
    }
    return children;
};

export default RequirePermission;
