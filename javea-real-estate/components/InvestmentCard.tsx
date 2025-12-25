import { Bed, Bath, Maximize, MapPin, TrendingUp } from 'lucide-react';
import type { Property } from '@/data/properties';

interface InvestmentCardProps {
  property: Property;
}

export default function InvestmentCard({ property }: InvestmentCardProps) {
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
        {/* ROI Badge */}
        {property.specs.roi && (
          <div className="absolute top-3 right-3 px-3 py-1 bg-green-500 text-white text-sm font-semibold rounded-full flex items-center gap-1">
            <TrendingUp className="w-4 h-4" />
            {property.specs.roi}% ROI
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

        {/* Specs */}
        <div className="flex items-center gap-4 text-sm text-muted pt-2 border-t border-border">
          {property.specs.bedrooms && (
            <div className="flex items-center gap-1">
              <Bed className="w-4 h-4" />
              <span>{property.specs.bedrooms} hab</span>
            </div>
          )}
          {property.specs.bathrooms && (
            <div className="flex items-center gap-1">
              <Bath className="w-4 h-4" />
              <span>{property.specs.bathrooms} baños</span>
            </div>
          )}
          <div className="flex items-center gap-1">
            <Maximize className="w-4 h-4" />
            <span>{property.specs.size}m²</span>
          </div>
        </div>
      </div>
    </div>
  );
}
