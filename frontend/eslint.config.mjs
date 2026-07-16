import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";
import prettier from "eslint-config-prettier";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

/** @type {import("eslint").Linter.Config[]} */
const eslintConfig = [
  { ignores: [".next/**", "out/**", "dist/**", "node_modules/**", "scripts/**"] },
  ...compat.extends("next/core-web-vitals"),
  {
    rules: {
      "@next/next/no-img-element": "off",
      "react/jsx-curly-brace-presence": ["error", { props: "never", children: "never" }],
      "react/self-closing-comp": "error",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
  prettier,
];

export default eslintConfig;
