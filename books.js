const BOOKS = [
  {
    slug: "postgresql-up-and-running",
    title: "PostgreSQL: Up and Running",
    author: "Regina Obe & Leo Hsu",
    pageCount: 231,
    description: "Thinking of migrating to PostgreSQL? This clear, fast-paced introduction helps you understand and use this enterprise-class open source database system.",
    cover: "books/postgresql-up-and-running/output/assets/images/page_0001_cover_full.png"
  },
  {
    slug: "sql-performance-explained",
    title: "SQL Performance Explained",
    author: "Markus Winand",
    pageCount: 207,
    description: "A developer's guide to SQL performance. Covers index structures, database optimization techniques, and slow queries.",
    cover: "books/sql-performance-explained/output/assets/images/page_0001_cover_photo.png"
  },
  {
    slug: "the-little-redis-book",
    title: "The Little Redis Book",
    author: "Karl Seguin",
    pageCount: 30,
    description: "A free, introductory book about Redis, the high-performance key-value store. Highly readable, conceptual database overview.",
    cover: "books/the-little-redis-book/output/assets/images/page_0001_cover_logo.png"
  },
  {
    slug: "designprinciplesandpatterns",
    title: "Design Principles and Patterns",
    author: "Robert C. Martin",
    pageCount: 34,
    description: "Robert C. Martin's guide to software design principles (SOLID) and patterns. Core concepts for robust object-oriented system engineering.",
    cover: null
  },
  {
    slug: "ocp-books",
    title: "OCP Books",
    author: "Oracle",
    pageCount: 747,
    description: "Oracle Certified Professional Java SE 17 & 21 Certification Study & Exam Preparation Guide (Chapters 12-24).",
    cover: null
  },
  {
    slug: "spring-microservices-in-action",
    title: "Spring Microservices in Action",
    author: "John Carnell",
    pageCount: 386,
    description: "A hands-on guide to building microservice-based applications using Java and Spring. Covers service discovery, configuration management, routing, and resilience patterns.",
    cover: "books/spring-microservices-in-action/output/assets/images/page_0001_cover_full.png"
  },
  {
    slug: "animal-farm-by-george-orwell",
    title: "Animal Farm",
    author: "George Orwell",
    pageCount: 108,
    description: "A satirical allegorical novella reflecting events leading up to the Russian Revolution and the Stalinist era of the Soviet Union. A timeless classic about power, corruption, and equality.",
    cover: "books/animal-farm-by-george-orwell/output/assets/cover.jpg"
  }
];

if (typeof module !== 'undefined' && module.exports) {
  module.exports = BOOKS;
}
