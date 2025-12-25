import { Home, TrendingUp, MapPin } from 'lucide-react';

export default function CategoryCards() {
  const categories = [
    {
      icon: Home,
      title: 'Casas y Pisos',
      description: 'Propiedades residenciales',
      href: '#casas',
    },
    {
      icon: TrendingUp,
      title: 'Oportunidades de Inversión',
      description: 'Proyectos con alta rentabilidad',
      href: '#inversiones',
    },
    {
      icon: MapPin,
      title: 'Parcelas',
      description: 'Terrenos edificables',
      href: '#parcelas',
    },
  ];

  return (
    <section className="container mx-auto px-4 py-16">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {categories.map((category, index) => {
          const Icon = category.icon;
          return (
            <a
              key={index}
              href={category.href}
              className="group relative bg-card border border-border rounded-xl p-8 hover:border-primary transition-all duration-300 hover-glow"
            >
              <div className="flex flex-col items-center text-center space-y-4">
                <div className="p-4 bg-gradient-to-br from-cyan-400/10 to-blue-500/10 rounded-lg group-hover:from-cyan-400/20 group-hover:to-blue-500/20 transition-colors">
                  <Icon className="w-8 h-8 text-primary" />
                </div>
                <h3 className="text-xl font-semibold">{category.title}</h3>
                <p className="text-muted text-sm">{category.description}</p>
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
