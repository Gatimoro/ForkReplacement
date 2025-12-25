import { Search } from 'lucide-react';

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center pt-20" id="inicio">
      {/* Background Image with Gradient Overlay */}
      <div className="absolute inset-0 z-0">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage:
              'url(https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=1920&h=1080&fit=crop)',
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/80 via-background/60 to-background" />
      </div>

      {/* Content */}
      <div className="relative z-10 container mx-auto px-4 text-center">
        <h1 className="text-5xl md:text-7xl font-bold mb-4">
          Encuentra tu lugar en{' '}
          <span className="gradient-text">Jávea</span>
        </h1>

        <div className="w-32 h-1 bg-gradient-to-r from-cyan-400 to-blue-500 mx-auto mb-6" />

        <p className="text-xl md:text-2xl text-muted mb-12 max-w-2xl mx-auto">
          Parcelas, obra nueva e inmuebles en la Costa Blanca
        </p>

        {/* Search Bar */}
        <div className="max-w-3xl mx-auto mb-16">
          <div className="relative">
            <input
              type="text"
              placeholder="Buscar propiedades en Jávea..."
              className="w-full px-6 py-4 pr-14 bg-white text-gray-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <button className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-primary text-white rounded-lg hover:bg-cyan-500 transition-colors">
              <Search className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="flex flex-wrap justify-center gap-8 text-center">
          <div className="flex items-center gap-2">
            <span className="text-3xl font-bold gradient-text">150+</span>
            <span className="text-muted">Propiedades</span>
          </div>
          <div className="hidden md:block text-muted">|</div>
          <div className="flex items-center gap-2">
            <span className="text-3xl font-bold gradient-text">50+</span>
            <span className="text-muted">Parcelas</span>
          </div>
          <div className="hidden md:block text-muted">|</div>
          <div className="flex items-center gap-2">
            <span className="text-3xl font-bold gradient-text">30+</span>
            <span className="text-muted">Proyectos</span>
          </div>
        </div>
      </div>

      {/* Bottom Gradient */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-background to-transparent z-5" />
    </section>
  );
}
