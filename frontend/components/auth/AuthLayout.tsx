import "@/app/auth.css";
import Brand from "@/components/Brand";

function RibbonBackdrop() {
  return <svg className="auth-ribbons" viewBox="0 0 920 1150" preserveAspectRatio="none" aria-hidden="true">
    <defs><linearGradient id="auth-ribbon" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#7544ff" stopOpacity=".04"/><stop offset=".5" stopColor="#6f32f1" stopOpacity=".33"/><stop offset="1" stopColor="#250d6c" stopOpacity=".04"/></linearGradient><filter id="auth-glow"><feGaussianBlur stdDeviation="5"/></filter></defs>
    <path d="M-100 35C280 230 125 370 470 540C695 655 820 720 980 570L960 600C720 870 350 590 210 410C75 240-20 235-100 150Z" fill="url(#auth-ribbon)"/>
    <path d="M-80 40C300 240 190 460 595 620C785 700 845 670 960 595" stroke="#7236ed" strokeWidth="2" opacity=".5"/>
    <path d="M-50 810C270 1110 530 766 965 1220L900 1340C515 850 40 1090-50 935Z" fill="url(#auth-ribbon)"/>
    <path d="M-100 1000C335 820 700 911 945 1190" stroke="#8950ff" strokeWidth="3" opacity=".7" filter="url(#auth-glow)"/>
    {Array.from({ length: 12 }, (_, index) => <path key={index} d={`M-100 ${1010 + index * 8}C335 ${825 + index * 8} 700 ${920 + index * 6} 945 ${1190 + index * 5}`} stroke="#8043f1" strokeWidth={index === 0 ? 1.7 : .7} opacity={index === 0 ? .85 : .16}/>) }
  </svg>;
}
export default function AuthLayout({ mode, children, demo = false }: { mode: "login" | "register"; children: React.ReactNode; demo?: boolean }) {
  return <div className={`auth-layout auth-${mode}`}><section className="auth-brand-panel" aria-label="About SignalX"><RibbonBackdrop/><div className="auth-brand-content"><Brand variant="stacked"/><h2>{mode === "login" ? "Find the signal in every conversation." : "Your next conversation starts here."}</h2><p>{mode === "login" ? "Evidence-led conversations. Thoughtful replies." : "Set up your account, then define your product."}</p></div></section><section className="auth-form-panel"><div className="auth-form-content"><span className="auth-eyebrow">{mode === "login" ? "Your workspace" : "Get started"}</span><h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1><p className="auth-subtitle">{mode === "login" ? "Sign in to continue to SignalX." : "A workspace for more relevant conversations."}</p>{children}</div><footer className="auth-footer">SignalX · {demo ? "Demo workspace" : "Local workspace"}</footer></section></div>;
}
