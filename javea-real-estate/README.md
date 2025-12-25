# Jávea Real Estate 🏖️

A modern, dark-themed real estate aggregation website for Jávea, Spain, built with Next.js 14, TypeScript, and Tailwind CSS.

![Hero Preview](https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=1200&h=400&fit=crop)

## 🎯 Features

- **Dark Theme Design** - Sleek near-black background with cyan/blue accents
- **Property Categories** - Houses, Investment Opportunities, and Land Plots
- **Responsive Carousels** - Horizontal scrolling property showcases
- **Modern UI/UX** - Glassmorphism effects, gradient text, and glow effects
- **Fully Responsive** - Mobile-first design that works on all devices
- **TypeScript** - Type-safe development experience
- **Performance Optimized** - Built with Next.js 14 App Router

## 📚 Framework Overview

### Next.js 14

Next.js is a React framework that provides:

- **App Router** - New routing system based on the file system (replaces Pages Router)
- **Server Components** - Components that render on the server by default (better performance)
- **Client Components** - Interactive components that run in the browser (marked with `'use client'`)
- **Automatic Code Splitting** - Only loads the JavaScript needed for each page
- **Built-in Optimization** - Image optimization, font optimization, and more
- **File-based Routing** - Create routes by adding files to the `app/` directory

**Key Concepts:**
- `app/layout.tsx` - Root layout that wraps all pages
- `app/page.tsx` - Home page component
- `'use client'` directive - Marks components that need browser interactivity (like `useState`, event handlers)

### TypeScript

TypeScript adds static typing to JavaScript:

- **Type Safety** - Catch errors before runtime
- **Better IDE Support** - Autocomplete, refactoring, and inline documentation
- **Interfaces** - Define the shape of objects (like our `Property` interface)
- **Type Inference** - TypeScript can often figure out types automatically

**Example:**
```typescript
interface Property {
  id: string;
  title: string;
  price: number;
  // ... TypeScript ensures we use these properties correctly
}
```

### Tailwind CSS

Utility-first CSS framework:

- **Utility Classes** - Small, single-purpose classes like `bg-blue-500`, `p-4`, `rounded-lg`
- **No Context Switching** - Style directly in your JSX/TSX
- **Responsive Design** - Built-in breakpoints (`md:`, `lg:`, etc.)
- **Custom Configuration** - Extend with custom colors, spacing, etc.

**Example:**
```tsx
<div className="bg-card border border-border rounded-xl p-5 hover:border-primary">
  // Tailwind classes for styling
</div>
```

### Lucide React

Icon library providing:
- 1000+ consistent, customizable icons
- React components for easy integration
- Small bundle size (tree-shakeable)

**Example:**
```tsx
import { Home, Search } from 'lucide-react';
<Home className="w-6 h-6 text-primary" />
```

## 🚀 Setup Instructions for Arch Linux

### 1. Install Node.js and npm

```bash
# Update system
sudo pacman -Syu

# Install Node.js and npm
sudo pacman -S nodejs npm

# Verify installation
node --version   # Should be v20.x or higher
npm --version    # Should be v10.x or higher
```

### 2. Clone and Navigate to Project

```bash
# Navigate to the project directory
cd javea-real-estate

# Verify you're in the right directory
ls -la  # Should see package.json, app/, components/, etc.
```

### 3. Install Dependencies

```bash
# Install all project dependencies
npm install

# This will install:
# - next (Next.js framework)
# - react & react-dom (React library)
# - typescript (TypeScript compiler)
# - tailwindcss (CSS framework)
# - lucide-react (Icon library)
# - And all dev dependencies
```

### 4. Run Development Server

```bash
# Start the development server
npm run dev

# The server will start on http://localhost:3000
# Open your browser and navigate to http://localhost:3000
```

**What happens during `npm run dev`:**
1. Next.js compiles your TypeScript files
2. Tailwind CSS processes your styles
3. Development server starts with hot reload (auto-refresh on file changes)
4. You can now see your changes instantly!

### 5. Build for Production (Optional)

```bash
# Create an optimized production build
npm run build

# Start the production server
npm start

# The production build is faster and optimized
```

## 📁 Project Structure

```
javea-real-estate/
├── app/                      # Next.js 14 App Router
│   ├── layout.tsx           # Root layout (wraps all pages)
│   ├── page.tsx             # Home page
│   └── globals.css          # Global styles & CSS variables
├── components/               # React components
│   ├── Navbar.tsx           # Navigation bar
│   ├── HeroSection.tsx      # Hero with search
│   ├── CategoryCards.tsx    # 3 category icons
│   ├── PropertyCard.tsx     # House/apartment card
│   ├── InvestmentCard.tsx   # Investment property card
│   ├── PlotCard.tsx         # Land plot card
│   ├── PropertyCarousel.tsx # Horizontal scrolling section
│   ├── CTASection.tsx       # Call-to-action section
│   └── Footer.tsx           # Footer
├── data/                     # Data and types
│   └── properties.ts        # Sample property data
├── public/                   # Static assets
├── tailwind.config.ts       # Tailwind configuration
├── tsconfig.json            # TypeScript configuration
├── next.config.js           # Next.js configuration
└── package.json             # Dependencies and scripts
```

## 🎨 Color Palette

The site uses CSS custom properties for easy theming:

```css
--background: #0a0a0f     /* Near-black background */
--card: #12121a           /* Dark card background */
--border: #1e1e2e         /* Subtle borders */
--primary: #06b6d4        /* Cyan accent */
--secondary: #3b82f6      /* Blue accent */
--foreground: #ffffff     /* White text */
--muted: #94a3b8          /* Muted gray text */
```

## 🛠️ Available Scripts

```bash
npm run dev      # Start development server (http://localhost:3000)
npm run build    # Build for production
npm start        # Start production server
npm run lint     # Run ESLint to check code quality
```

## 📦 Data Structure

Properties are defined in `data/properties.ts`:

```typescript
interface Property {
  id: string;
  type: 'house' | 'investment' | 'plot';
  title: string;
  price: number;
  location: string;
  image: string;
  badge?: string;
  specs: {
    bedrooms?: number;
    bathrooms?: number;
    size: number;
    plotSize?: number;
    roi?: number;
    zone?: string;
    buildable?: boolean;
  };
}
```

Currently using placeholder images from Unsplash. Replace with real property images later.

## 🔧 Customization Tips

### Adding New Properties

Edit `data/properties.ts`:

```typescript
export const houses: Property[] = [
  {
    id: 'h7',
    type: 'house',
    title: 'Your new property',
    price: 500000,
    // ... add your property details
  },
  // ... existing properties
];
```

### Changing Colors

Edit `app/globals.css`:

```css
:root {
  --primary: #your-color;  /* Change primary accent */
}
```

### Adding New Sections

1. Create a new component in `components/`
2. Import and add it to `app/page.tsx`

## 🌐 Deployment

### Deploy to Vercel (Recommended)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel

# Follow the prompts
```

### Deploy to Other Platforms

The production build (`npm run build`) creates a `.next` folder that can be deployed to:
- Vercel (zero-config)
- Netlify
- Railway
- Your own server (requires Node.js)

## 📱 Responsive Breakpoints

Tailwind's default breakpoints:

- `sm`: 640px (small tablets)
- `md`: 768px (tablets)
- `lg`: 1024px (laptops)
- `xl`: 1280px (desktops)
- `2xl`: 1536px (large screens)

**Example:**
```tsx
<div className="grid grid-cols-1 md:grid-cols-3 gap-6">
  {/* 1 column on mobile, 3 columns on tablet+ */}
</div>
```

## 🐛 Troubleshooting

### Port 3000 already in use

```bash
# Kill the process using port 3000
sudo lsof -ti:3000 | xargs kill -9

# Or use a different port
npm run dev -- -p 3001
```

### Module not found errors

```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

### TypeScript errors

```bash
# Check TypeScript configuration
npx tsc --noEmit

# Often fixed by restarting your editor
```

## 🚀 Next Steps

Now that you have the shell working, here are some ideas for expansion:

1. **Add Search Functionality** - Make the search bar functional
2. **Property Detail Pages** - Click on a property to see full details
3. **Filters** - Add price range, bedrooms, location filters
4. **Contact Forms** - Add inquiry forms for properties
5. **Admin Panel** - Create interface to manage properties
6. **Database Integration** - Connect to PostgreSQL/MongoDB
7. **Authentication** - Add user accounts and favorites
8. **Map Integration** - Show properties on a map
9. **Image Gallery** - Multiple images per property
10. **Multi-language** - Add English version

## 📄 License

This project is open source and available for educational purposes.

## 🤝 Contributing

This is a starting point for your project. Feel free to customize and expand!

---

**Built with ❤️ for Jávea, Spain**
