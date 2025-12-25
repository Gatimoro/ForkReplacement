import Navbar from '@/components/Navbar';
import HeroSection from '@/components/HeroSection';
import CategoryCards from '@/components/CategoryCards';
import PropertyCarousel from '@/components/PropertyCarousel';
import CTASection from '@/components/CTASection';
import Footer from '@/components/Footer';
import { houses, investments, plots } from '@/data/properties';

export default function Home() {
  return (
    <main className="relative min-h-screen">
      <Navbar />
      <HeroSection />
      <CategoryCards />
      <PropertyCarousel
        title="Casas y Pisos"
        properties={houses}
        id="casas"
      />
      <PropertyCarousel
        title="Oportunidades de Inversión"
        properties={investments}
        id="inversiones"
      />
      <PropertyCarousel title="Parcelas" properties={plots} id="parcelas" />
      <CTASection />
      <Footer />
    </main>
  );
}
