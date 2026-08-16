{ pkgs, ... }:

{
  programs.neovim = {
    enable = true;
    defaultEditor = true;
    vimAlias = true;
    withPython3 = false;
    withRuby = false;

    extraPackages = with pkgs; [
      # fzf-lua が呼ぶ外部コマンド。本体は home.packages にもあるが、
      # nvim 単体起動でも PATH が欠けないようここでも渡す。
      ripgrep
      fd
      fzf
      (callPackage ../../pkgs/hunk { })
    ];

    plugins = with pkgs.vimPlugins; [
      nvim-lspconfig
      nvim-treesitter.withAllGrammars
      fzf-lua
      nvim-web-devicons
      lualine-nvim
      which-key-nvim
      gitsigns-nvim
      yazi-nvim
      lazygit-nvim
      plenary-nvim
    ];

    initLua = ''
      vim.g.mapleader = " "
      vim.g.maplocalleader = " "

      vim.opt.number = true
      vim.opt.relativenumber = true
      vim.opt.mouse = "a"
      vim.opt.clipboard = "unnamedplus"
      vim.opt.ignorecase = true
      vim.opt.smartcase = true
      vim.opt.expandtab = true
      vim.opt.shiftwidth = 2
      vim.opt.tabstop = 2
      vim.opt.signcolumn = "yes"
      vim.opt.undofile = true
      vim.opt.splitright = true
      vim.opt.splitbelow = true
      vim.opt.termguicolors = true
      vim.opt.scrolloff = 8
      vim.opt.updatetime = 250
      vim.opt.cursorline = true
      vim.opt.cursorlineopt = "line,number"
      vim.opt.laststatus = 3
      vim.opt.showmode = false
      vim.opt.showtabline = 0
      vim.opt.winborder = "rounded"
      vim.opt.fillchars = {
        eob = " ",
        fold = " ",
        foldopen = "",
        foldclose = "",
        foldsep = " ",
        diff = "╱",
      }

      -- Ghostty の透明な aqua glass を背景として活かしつつ、Pi の
      -- midnight-ocean palette を syntax / panel / statusline に適用する。
      local ocean = {
        deep = "#0a192f",
        card = "#112240",
        blue = "#0077be",
        teal = "#00ced1",
        cyan = "#4fd1ed",
        text = "#e6f1ff",
        border = "#233554",
        dim = "#c5cde0",
        muted = "#b4bed8",
        green = "#64ffda",
        red = "#ff5f56",
        amber = "#ffd700",
        purple = "#c678dd",
      }

      local hi = function(group, opts)
        vim.api.nvim_set_hl(0, group, opts)
      end

      vim.cmd.colorscheme("habamax")

      -- editor surface: transparent so Ghostty blur/background remains visible
      hi("Normal", { fg = ocean.text, bg = "NONE" })
      hi("NormalNC", { fg = ocean.dim, bg = "NONE" })
      hi("SignColumn", { bg = "NONE" })
      hi("FoldColumn", { fg = ocean.border, bg = "NONE" })
      hi("EndOfBuffer", { fg = ocean.border, bg = "NONE" })
      hi("LineNr", { fg = ocean.border, bg = "NONE" })
      hi("CursorLineNr", { fg = ocean.teal, bg = "NONE", bold = true })
      hi("CursorLine", { bg = "#16324f" })
      hi("Visual", { bg = "#1b4f6f" })
      hi("Search", { fg = ocean.deep, bg = ocean.amber, bold = true })
      hi("IncSearch", { fg = ocean.deep, bg = ocean.teal, bold = true })
      hi("MatchParen", { fg = ocean.teal, bg = ocean.border, bold = true })
      hi("WinSeparator", { fg = ocean.border, bg = "NONE" })

      -- Pi-like card surfaces for floating UI
      hi("NormalFloat", { fg = ocean.text, bg = ocean.card })
      hi("FloatBorder", { fg = ocean.teal, bg = ocean.card })
      hi("FloatTitle", { fg = ocean.teal, bg = ocean.card, bold = true })
      hi("Pmenu", { fg = ocean.text, bg = ocean.card })
      hi("PmenuSel", { fg = ocean.text, bg = ocean.blue, bold = true })
      hi("PmenuSbar", { bg = ocean.border })
      hi("PmenuThumb", { bg = ocean.teal })

      -- Pi midnight-ocean syntax palette
      hi("Comment", { fg = ocean.muted, italic = true })
      hi("Constant", { fg = ocean.amber })
      hi("String", { fg = ocean.green })
      hi("Number", { fg = ocean.amber })
      hi("Identifier", { fg = ocean.cyan })
      hi("Function", { fg = ocean.teal })
      hi("Statement", { fg = ocean.purple, bold = true })
      hi("Keyword", { fg = ocean.purple, bold = true })
      hi("Operator", { fg = ocean.teal })
      hi("Type", { fg = ocean.blue, bold = true })
      hi("Special", { fg = ocean.cyan })
      hi("Delimiter", { fg = ocean.dim })

      hi("@comment", { link = "Comment" })
      hi("@string", { link = "String" })
      hi("@number", { link = "Number" })
      hi("@variable", { fg = ocean.cyan })
      hi("@variable.builtin", { fg = ocean.cyan, italic = true })
      hi("@function", { fg = ocean.teal })
      hi("@function.call", { fg = ocean.teal })
      hi("@keyword", { fg = ocean.purple, bold = true })
      hi("@type", { fg = ocean.blue })
      hi("@operator", { fg = ocean.teal })
      hi("@punctuation", { fg = ocean.dim })

      hi("DiagnosticError", { fg = ocean.red })
      hi("DiagnosticWarn", { fg = ocean.amber })
      hi("DiagnosticInfo", { fg = ocean.cyan })
      hi("DiagnosticHint", { fg = ocean.green })
      hi("GitSignsAdd", { fg = ocean.green })
      hi("GitSignsChange", { fg = ocean.cyan })
      hi("GitSignsDelete", { fg = ocean.red })

      -- 迷ったら Esc。検索ハイライトも Esc で消す。
      vim.keymap.set("n", "<Esc>", "<cmd>nohlsearch<CR>")

      -- nvim-treesitter 0.10+ (main): highlight は filetype ごとに start する。
      -- parser が無い言語は pcall で無視。
      vim.api.nvim_create_autocmd("FileType", {
        group = vim.api.nvim_create_augroup("user-treesitter", { clear = true }),
        callback = function(ev)
          pcall(vim.treesitter.start, ev.buf)
        end,
      })

      local wk = require("which-key")
      wk.setup({
        delay = 400,
        win = { border = "rounded", padding = { 1, 2 } },
        icons = { breadcrumb = "›", separator = "➜", group = "+" },
      })
      wk.add({
        { "<leader>f", group = "find" },
        { "<leader>g", group = "git" },
        { "<leader>h", group = "hunk" },
        { "<leader>c", group = "code" },
        { "<leader>b", group = "buffer" },
      })

      require("fzf-lua").setup({
        winopts = {
          height = 0.78,
          width = 0.88,
          row = 0.50,
          col = 0.50,
          border = "rounded",
          preview = { layout = "vertical", vertical = "down:45%" },
        },
        fzf_opts = {
          ["--layout"] = "reverse",
          ["--info"] = "inline-right",
          ["--pointer"] = "●",
          ["--marker"] = "✓",
        },
      })
      vim.keymap.set("n", "<leader>ff", "<cmd>FzfLua files<CR>", { desc = "Find files" })
      vim.keymap.set("n", "<leader>fg", "<cmd>FzfLua live_grep<CR>", { desc = "Search in files" })
      vim.keymap.set("n", "<leader>fb", "<cmd>FzfLua buffers<CR>", { desc = "Buffers" })
      vim.keymap.set("n", "<leader>fh", "<cmd>FzfLua helptags<CR>", { desc = "Help" })
      vim.keymap.set("n", "<leader>fr", "<cmd>FzfLua oldfiles<CR>", { desc = "Recent files" })

      require("lualine").setup({
        options = {
          theme = {
            normal = {
              a = { fg = ocean.deep, bg = ocean.teal, gui = "bold" },
              b = { fg = ocean.text, bg = ocean.blue },
              c = { fg = ocean.dim, bg = ocean.card },
            },
            insert = { a = { fg = ocean.deep, bg = ocean.green, gui = "bold" } },
            visual = { a = { fg = ocean.deep, bg = ocean.purple, gui = "bold" } },
            replace = { a = { fg = ocean.deep, bg = ocean.red, gui = "bold" } },
            command = { a = { fg = ocean.deep, bg = ocean.amber, gui = "bold" } },
            inactive = {
              a = { fg = ocean.muted, bg = ocean.card },
              b = { fg = ocean.muted, bg = ocean.card },
              c = { fg = ocean.muted, bg = ocean.card },
            },
          },
          globalstatus = true,
          component_separators = { left = "│", right = "│" },
          section_separators = { left = "", right = "" },
        },
        sections = {
          lualine_a = { { "mode", fmt = function(s) return s:sub(1, 1) end } },
          lualine_b = { "branch", "diff" },
          lualine_c = { { "filename", path = 1, symbols = { modified = " ●", readonly = " " } } },
          lualine_x = { "diagnostics", "filetype" },
          lualine_y = { "progress" },
          lualine_z = { "location" },
        },
      })

      require("gitsigns").setup({
        signs = {
          add = { text = "▎" },
          change = { text = "▎" },
          delete = { text = "" },
        },
      })

      require("yazi").setup({
        open_for_directories = false,
      })
      vim.keymap.set("n", "<leader>e", "<cmd>Yazi<CR>", { desc = "File explorer" })
      vim.keymap.set("n", "<leader>E", "<cmd>Yazi cwd<CR>", { desc = "File explorer (cwd)" })

      vim.keymap.set("n", "<leader>gg", "<cmd>LazyGit<CR>", { desc = "Lazygit" })
      vim.keymap.set("n", "<leader>hd", "<cmd>terminal hunk diff<CR>", { desc = "Hunk review (working tree)" })
      vim.keymap.set("n", "<leader>hs", "<cmd>terminal hunk show<CR>", { desc = "Hunk review (latest commit)" })

      vim.keymap.set("n", "<leader>bd", "<cmd>bdelete<CR>", { desc = "Close buffer" })
      vim.keymap.set("n", "<leader>bn", "<cmd>bnext<CR>", { desc = "Next buffer" })
      vim.keymap.set("n", "<leader>bp", "<cmd>bprevious<CR>", { desc = "Previous buffer" })

      -- home.packages に入っている LSP だけ有効化。未 install のサーバは足さない。
      vim.lsp.enable({ "pyright", "ruff", "nil_ls", "biome", "terraformls" })

      vim.api.nvim_create_autocmd("LspAttach", {
        group = vim.api.nvim_create_augroup("user-lsp", { clear = true }),
        callback = function(ev)
          local map = function(keys, fn, desc)
            vim.keymap.set("n", keys, fn, { buffer = ev.buf, desc = desc })
          end
          map("gd", vim.lsp.buf.definition, "Go to definition")
          map("gr", vim.lsp.buf.references, "References")
          map("K", vim.lsp.buf.hover, "Hover")
          map("<leader>ca", vim.lsp.buf.code_action, "Code action")
          map("<leader>cr", vim.lsp.buf.rename, "Rename")
          map("<leader>cf", function()
            vim.lsp.buf.format({ async = true })
          end, "Format")
        end,
      })

      vim.diagnostic.config({
        virtual_text = true,
        severity_sort = true,
      })
    '';
  };
}
