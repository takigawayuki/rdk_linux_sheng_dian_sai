declare module "lucide/dist/esm/icons/*.js" {
  type IconNode = [string, Record<string, string | number>, IconNode[]?];
  const iconNode: IconNode;
  export default iconNode;
}

declare module "lucide/dist/esm/createElement.js" {
  type IconNode = [string, Record<string, string | number>, IconNode[]?];
  const createElement: (node: IconNode) => SVGElement;
  export default createElement;
}
