import { Maximize, MapPin, CheckCircle, XCircle } from 'lucide-react';
import type { Property } from '@/data/properties';

interface PlotCardProps {
  property: Property;
}

export default function PlotCard({ property }: PlotCardProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(price);
  };

  return (
    <div className="group flex-shrink-0 w-80 bg-card border border-border rounded-xl overflow-hidden hover:border-primary transition-all duration-300 hover-glow">
      {/* Image */}
      <div className="relative h-48 overflow-hidden">
        <img
          src={property.image}
          alt={property.title}
          className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-300"
        />
        {property.badge && (
          <div className="absolute top-3 left-3 px-3 py-1 bg-primary text-white text-sm font-semibold rounded-full">
            {property.badge}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-5 space-y-3">
        {/* Price */}
        <div className="text-2xl font-bold gradient-text">
          {formatPrice(property.price)}
        </div>

        {/* Title */}
        <h3 className="text-lg font-semibold line-clamp-1">{property.title}</h3>

        {/* Location */}
        <div className="flex items-center text-muted text-sm">
          <MapPin className="w-4 h-4 mr-1" />
          <span className="line-clamp-1">{property.location}</span>
        </div>

        {/* Plot Specs */}
        <div className="space-y-2 pt-2 border-t border-border">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted flex items-center gap-1">
              <Maximize className="w-4 h-4" />
              Tamaño:
            </span>
            <span className="font-semibold">{property.specs.size}m²</span>
          </div>

          {property.specs.buildable !== undefined && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">Edificable:</span>
              <span className="flex items-center gap-1">
                {property.specs.buildable ? (
                  <>
                    <CheckCircle className="w-4 h-4 text-green-500" />
                    <span className="text-green-500">Sí</span>
                  </>
                ) : (
                  <>
                    <XCircle className="w-4 h-4 text-red-500" />
                    <span className="text-red-500">No</span>
                  </>
                )}
              </span>
            </div>
          )}

          {property.specs.zone && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">Zona:</span>
              <span className="font-semibold">{property.specs.zone}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
