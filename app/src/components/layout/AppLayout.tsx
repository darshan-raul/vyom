import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  DollarSign,
  PiggyBank,
  Boxes,
  Shield,
  Bug,
  ClipboardCheck,
  Bell,
  MessageSquare,
  Settings,
  LogOut,
} from "lucide-react";
import { useSession } from "@/auth/useSession";
import { hasRole, type Role } from "@/lib/roles";
import { logout as keycloakLogout } from "@/auth/keycloak";
import { setSession } from "@/auth/session";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { PRODUCT_NAME } from "@/lib/brand";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  minRole: Role;
}

const NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, minRole: "viewer" },
  { to: "/costs", label: "Costs", icon: DollarSign, minRole: "viewer" },
  { to: "/finops", label: "FinOps", icon: PiggyBank, minRole: "viewer" },
  { to: "/inventory", label: "Inventory", icon: Boxes, minRole: "viewer" },
  { to: "/security", label: "Security", icon: Shield, minRole: "operator" },
  { to: "/sca", label: "SCA", icon: Bug, minRole: "operator" },
  { to: "/compliance", label: "Compliance", icon: ClipboardCheck, minRole: "operator" },
  { to: "/alerts", label: "Alerts", icon: Bell, minRole: "operator" },
  { to: "/chat", label: "Chat", icon: MessageSquare, minRole: "viewer" },
  { to: "/settings", label: "Settings", icon: Settings, minRole: "admin" },
];

export function AppLayout() {
  const { session } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  if (!session) {
    navigate("/login", { replace: true });
    return null;
  }

  const handleLogout = () => {
    setSession(null);
    keycloakLogout({ redirectUri: window.location.origin + "/login" });
  };

  return (
    <div className="flex h-full">
      <aside className="hidden md:flex w-64 flex-col border-r bg-card">
        <div className="flex items-center gap-2 p-4 border-b">
          <span aria-hidden="true" className="text-xl font-semibold text-primary">V</span>
          <div className="font-semibold">{PRODUCT_NAME}</div>
        </div>
        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {NAV.filter((n) => hasRole(session, n.minRole)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                )
              }
            >
              <n.icon className="h-4 w-4" />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <Separator />
        <div className="p-3 flex items-center gap-2">
          <Avatar>
            <AvatarFallback>{session.username.slice(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">{session.username}</div>
            <div className="flex flex-wrap gap-1">
              {session.roles.map((r) => (
                <Badge key={r} variant="secondary" className="text-[10px]">
                  {r}
                </Badge>
              ))}
            </div>
          </div>
          <Button size="icon" variant="ghost" onClick={handleLogout} aria-label="Logout">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="container py-6">
          <Outlet key={location.pathname} />
        </div>
      </main>
    </div>
  );
}
