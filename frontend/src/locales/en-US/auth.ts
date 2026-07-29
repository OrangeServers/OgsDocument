import type zh from '../zh-CN/auth'

export default {
  brand: {
    slogan: 'AI operations platform · Mission Control',
  },
  field: {
    username: 'Username',
    password: 'Password',
    captcha: 'Captcha',
    email: 'Email',
    emailCode: 'Email code',
    newPassword: 'New password',
    setPassword: 'Password',
    confirmPassword: 'Confirm password',
  },
  placeholder: {
    username: 'Enter username',
    password: 'Enter password',
    captchaResult: 'Enter the result',
  },
  validation: {
    usernameRequired: 'Please enter a username',
    passwordRequired: 'Please enter a password',
    captchaRequired: 'Please enter the captcha',
    captchaNumeric: 'Enter the result as a number',
    emailRequired: 'Please enter an email',
    emailFormat: 'Invalid email format',
    newPasswordRequired: 'Please enter a new password',
    newPasswordMin: 'Password must be at least 6 characters',
    passwordMin8: 'Password must be at least 8 characters',
    confirmPasswordRequired: 'Please confirm the password',
  },
  login: {
    brandTitleLead: 'Make operations',
    brandTitleAccent: 'simple and controlled',
    brandDescLine1: 'Manage server assets, batch commands and scripts from one console,',
    brandDescLine2: 'with every action audited, traceable, and alertable.',
    feature1: 'Centralized asset management',
    feature2: 'Batch command and script delivery',
    feature3: 'Full operation audit and session recording',
    title: 'Welcome back',
    subtitle: 'Sign in to the OrangeServer console with your account',
    captchaRefresh: 'Click for a new question',
    submit: 'Sign in',
    submitLocked: 'Sign-in disabled ({s}s)',
    registerNow: 'Sign up',
    forgotPassword: 'Forgot password?',
    lockedRetry: 'Sign-in temporarily disabled, retry in {s}s',
    captchaNotLoaded: 'Captcha not loaded, click to refresh',
    success: 'Signed in',
    failLocked: '{n} consecutive failures, sign-in disabled for {s}s',
    fail: 'Sign-in failed',
    failWithReason: 'Sign-in failed: {msg}',
    serverError: 'Server error ({status})',
    networkError: 'Network error',
  },
  forgot: {
    title: 'Reset password',
    emailPlaceholder: 'Enter your registered email',
    codePlaceholder: '6-digit email code',
    newPasswordPlaceholder: 'Enter a new password',
    sendCode: 'Send code',
    submit: 'Reset password',
    emailFirst: 'Enter your email first',
    codeSent: 'Code sent',
    sendFail: 'Failed to send',
    resetSuccess: 'Password reset, please sign in again',
    resetFail: 'Reset failed',
  },
  register: {
    brandTitleLead: 'Start your',
    brandTitleAccent: 'operations journey',
    brandDescLine1: 'Create an account, join your team,',
    brandDescLine2: 'and start managing assets, commands, and scripts in one place.',
    step1Name: 'Fill in basic info',
    step1Desc: 'Username, email, and password',
    step2Name: 'Verify your email',
    step2Desc: 'Use the code in the email to activate',
    step3Name: 'Start managing assets',
    step3Desc: 'Sign in to the console, add hosts and users',
    title: 'Create account',
    subtitle: 'Start managing your servers in minutes',
    check: 'Check',
    emailPlaceholder: 'Used to receive the activation code',
    codePlaceholder: 'Enter the 6-digit code from the email',
    getCode: 'Get code',
    resendIn: 'Retry in {s}s',
    passwordPlaceholder: 'At least 8 characters, letters and digits',
    confirmPlaceholder: 'Enter the password again',
    strengthLabel: 'Password strength: ',
    pwMismatch: 'Passwords do not match',
    agreePrefix: 'I have read and agree to the',
    agreeAnd: 'and',
    terms: 'Terms of Service',
    privacy: 'Privacy Policy',
    submit: 'Create account',
    haveAccount: 'Already have an account?',
    loginNow: 'Sign in',
    acknowledged: 'Got it',
    usernameFirst: 'Enter a username first',
    usernameAvailable: 'Username is available',
    usernameTaken: 'Username already exists',
    emailFirst: 'Enter your email first',
    codeSent: 'Code sent, check your inbox',
    sendFail: 'Failed to send',
    pwTooWeak: 'Password too weak, combine letters, digits, and special characters',
    success: 'Registered, please sign in',
    fail: 'Registration failed',
    requestFail: 'Registration request failed',
    termsContent: `OrangeServer Terms of Service (sample)

1. Scope: this platform provides server asset management, command execution, and auditing.
2. Usage: users must follow their organization's security policies and must not use it for unauthorized access.
3. Liability: data loss or business impact caused by misoperation is the user's own responsibility.
4. Account security: keep your password safe; the platform never stores plaintext passwords (one-way hash).

(This is placeholder sample text; real legal terms can be linked here later.)`,
    privacyContent: `OrangeServer Privacy Policy (sample)

1. Data collected: username and email at registration; IP / device / time at sign-in.
2. Data usage: authentication, operation auditing, and security alerts; never shared with third parties.
3. Password storage: one-way hashed (PBKDF2/bcrypt or similar); no plaintext is kept.
4. Cookies: sessions use HttpOnly cookies that JS cannot read, preventing XSS theft.

(This is placeholder sample text; real privacy policy can be linked here later.)`,
  },
} satisfies typeof zh
