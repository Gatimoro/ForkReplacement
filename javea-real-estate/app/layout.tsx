import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Jávea Real Estate - Encuentra tu lugar en la Costa Blanca',
  description:
    'Descubre casas, pisos, parcelas y oportunidades de inversión en Jávea, España. Tu portal de confianza para propiedades en la Costa Blanca.',
  keywords: [
    'jávea',
    'real estate',
    'costa blanca',
    'propiedades',
    'casas',
    'pisos',
    'parcelas',
    'inversión',
    'españa',
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="scroll-smooth">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
