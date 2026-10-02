import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { KeyRound } from "lucide-react";
import { PRODUCT_NAME, EXECUTIVE_TAGLINE } from "@/lib/brand";
import { useSession } from "@/auth/useSession";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

export function LoginPage() {
  const { session, loading } = useSession();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && session) navigate("/", { replace: true });
  }, [session, loading, navigate]);

  const signIn = () => {
    sessionStorage.setItem("kc_attempt", "1");
    window.location.reload();
  };

  return (
    <div className="h-full grid place-items-center">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <span aria-hidden="true" className="text-2xl font-semibold text-primary">V</span>
          </div>
          <CardTitle>{PRODUCT_NAME}</CardTitle>
          <CardDescription>{EXECUTIVE_TAGLINE}</CardDescription>
          <p className="text-sm text-muted-foreground">Sign in with your organization&apos;s SSO.</p>
        </CardHeader>
        <CardContent>
          <Button className="w-full" onClick={signIn}>
            <KeyRound className="mr-2 h-4 w-4" /> Continue with Keycloak
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
