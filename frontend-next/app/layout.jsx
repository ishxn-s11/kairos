import "./globals.css";
import Chrome from "../components/Chrome";
import Boot from "../components/Boot";

export const metadata = {
  /* Placeholder deploy origin — replace with the real production URL. */
  metadataBase: new URL("https://kairos-buy-or-wait.example.com"),
  title: "KAIROS — Financial Affordability Agent",
  description: "KAIROS — AI-powered financial affordability agent (Buy or Wait? — HackerRank Orchestrate September 2026)",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/assets/img/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/assets/img/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/assets/img/icon-180.png",
  },
  openGraph: {
    type: "website",
    siteName: "KAIROS",
    title: "KAIROS — Financial Affordability Agent",
    description: "KAIROS — AI-powered financial affordability agent (Buy or Wait? — HackerRank Orchestrate September 2026)",
    url: "/",
    images: [{ url: "/assets/img/og-image.png", width: 1200, height: 630, alt: "KAIROS — Buy or Wait?" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "KAIROS — Financial Affordability Agent",
    description: "KAIROS — AI-powered financial affordability agent (Buy or Wait? — HackerRank Orchestrate September 2026)",
    images: ["/assets/img/og-image.png"],
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var saved=localStorage.getItem('kairos-theme');var theme=saved||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=theme;document.documentElement.style.colorScheme=theme}catch(e){document.documentElement.dataset.theme='light'}})();` }} />
      </head>
      <body>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet" />
        <audio id="ambience" loop preload="none">
          <source src="/assets/audio/ambience.wav" type="audio/wav" />
        </audio>
        <Chrome />
        {children}
        <Boot />
      </body>
    </html>
  );
}
