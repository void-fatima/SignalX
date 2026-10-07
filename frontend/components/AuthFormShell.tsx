import SignInForm from "./auth/SignInForm";
import SignUpForm from "./auth/SignUpForm";

export default function AuthFormShell({ mode }: { mode: "login" | "register" }) {
  return mode === "login" ? <SignInForm/> : <SignUpForm/>;
}
