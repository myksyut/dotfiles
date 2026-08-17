{
  description = "miyakishota's macOS + Windows(WSL) configuration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    nix-darwin = {
      url = "github:LnL7/nix-darwin";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixos-wsl = {
      url = "github:nix-community/NixOS-WSL/main";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-index-database = {
      url = "github:nix-community/nix-index-database";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # zeno.zsh (zsh snippet/補完プラグイン)。flake ではないので source tree だけもらう。
    # 実行時に deno が node_modules を生成するため writable copy が必要 (modules/home の activation 参照)。
    zeno-zsh = {
      url = "github:yuki-yano/zeno.zsh/37bebf0e1737de000abe0d58f70d41b8ef61f9b4";
      flake = false;
    };
    # Custom Pi orchestration package. Override with
    # `--override-input agent-pi path:$HOME/src/agent-pi` while developing.
    agent-pi = {
      url = "github:myksyut/agent-pi";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nix-darwin,
      nixos-wsl,
      home-manager,
      nix-index-database,
      treefmt-nix,
      git-hooks,
      zeno-zsh,
      agent-pi,
    }:
    let
      # ---- macOS (nix-darwin) ----
      darwinSystem = "aarch64-darwin";
      darwinHostname = "miyagishoutanoMacBook-Pro";

      # ---- Windows (WSL / NixOS-WSL) ----
      # WSL distro 名。`wsl -d <name>` で起動する識別子。Hostname としても利用。
      wslSystem = "x86_64-linux";
      wslHostname = "miyaki-wsl";

      username = "miyakishota";

      mkPkgs =
        system:
        import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

      darwinPkgs = mkPkgs darwinSystem;
      wslPkgs = mkPkgs wslSystem;

      # ---- 共通: treefmt / pre-commit を system ごとに評価 ----
      mkTreefmtEval =
        pkgs:
        treefmt-nix.lib.evalModule pkgs {
          projectRootFile = "flake.nix";
          programs = {
            nixfmt.enable = true;
            statix.enable = true;
            deadnix.enable = true;
          };
        };

      mkPreCommitCheck =
        system:
        git-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            treefmt = {
              enable = true;
              package = (mkTreefmtEval (mkPkgs system)).config.build.wrapper;
            };
            statix.enable = true;
            deadnix.enable = true;
          };
        };

      darwinTreefmtEval = mkTreefmtEval darwinPkgs;
      wslTreefmtEval = mkTreefmtEval wslPkgs;

      darwinPreCommitCheck = mkPreCommitCheck darwinSystem;
      wslPreCommitCheck = mkPreCommitCheck wslSystem;

      # ---- 共通の home-manager 設定 (どちらの OS でも同じ modules/home を読む) ----
      homeManagerModule = {
        home-manager = {
          useGlobalPkgs = true;
          useUserPackages = true;
          # 管理対象パスに既存ファイルがある場合は <file>.before-nix.backup へ退避してから link
          backupFileExtension = "before-nix.backup";
          extraSpecialArgs = {
            inherit username zeno-zsh agent-pi;
          };
          users.${username} = {
            imports = [
              nix-index-database.homeModules.nix-index
              ./modules/home
            ];
          };
        };
      };
    in
    {
      # ===========================================================
      # macOS
      # ===========================================================
      darwinConfigurations.${darwinHostname} = nix-darwin.lib.darwinSystem {
        system = darwinSystem;
        specialArgs = { inherit username; };
        modules = [
          ./modules/darwin
          home-manager.darwinModules.home-manager
          homeManagerModule
        ];
      };

      # ===========================================================
      # Windows (NixOS-WSL)
      # `wsl --install -d NixOS` で distro を入れた直後、ホスト名を `wslHostname` に
      # 合わせて初回 `nixos-rebuild switch --flake .#${wslHostname}` で適用する。
      # ===========================================================
      nixosConfigurations.${wslHostname} = nixpkgs.lib.nixosSystem {
        system = wslSystem;
        specialArgs = { inherit username; };
        modules = [
          nixos-wsl.nixosModules.default
          ./modules/nixos
          home-manager.nixosModules.home-manager
          homeManagerModule
          { networking.hostName = wslHostname; }
        ];
      };

      # ===========================================================
      # apps: macOS
      # ===========================================================
      apps.${darwinSystem} = {
        switch = {
          type = "app";
          program = toString (
            darwinPkgs.writeShellScript "darwin-switch" ''
              set -eo pipefail
              echo "==> Building and switching darwin configuration..."
              # 固定パスの darwin-rebuild を使う (sudoers の NOPASSWD ルールがマッチするように)
              sudo /run/current-system/sw/bin/darwin-rebuild \
                switch --flake "${self}#${darwinHostname}" \
                |& ${darwinPkgs.nix-output-monitor}/bin/nom
              echo "==> Done!"
            ''
          );
        };

        build = {
          type = "app";
          program = toString (
            darwinPkgs.writeShellScript "darwin-build" ''
              set -eo pipefail
              echo "==> Building darwin configuration (no switch)..."
              ${darwinPkgs.nix-output-monitor}/bin/nom build "${self}#darwinConfigurations.${darwinHostname}.system"
              echo "==> Build successful! Run 'nix run .#switch' to apply."
            ''
          );
        };

        update = {
          type = "app";
          program = toString (
            darwinPkgs.writeShellScript "flake-update" ''
              set -e
              cd ~/.config/nix-config
              echo "==> Updating flake.lock..."
              nix flake update
              echo "==> Done! Run 'nix run .#switch' to apply."
            ''
          );
        };

        fmt = {
          type = "app";
          program = toString (
            darwinPkgs.writeShellScript "treefmt-wrapper" ''
              exec ${darwinTreefmtEval.config.build.wrapper}/bin/treefmt "$@"
            ''
          );
        };
      };

      # ===========================================================
      # apps: Windows (WSL / x86_64-linux)
      # `nix run .#switch` を WSL から実行すると nixos-rebuild に切り替わる。
      # ===========================================================
      apps.${wslSystem} = {
        switch = {
          type = "app";
          program = toString (
            wslPkgs.writeShellScript "wsl-switch" ''
              set -eo pipefail
              echo "==> Building and switching NixOS-WSL configuration..."
              sudo /run/current-system/sw/bin/nixos-rebuild \
                switch --flake "${self}#${wslHostname}" \
                |& ${wslPkgs.nix-output-monitor}/bin/nom
              echo "==> Done!"
            ''
          );
        };

        build = {
          type = "app";
          program = toString (
            wslPkgs.writeShellScript "wsl-build" ''
              set -eo pipefail
              echo "==> Building NixOS-WSL configuration (no switch)..."
              ${wslPkgs.nix-output-monitor}/bin/nom build "${self}#nixosConfigurations.${wslHostname}.config.system.build.toplevel"
              echo "==> Build successful! Run 'nix run .#switch' to apply."
            ''
          );
        };

        update = {
          type = "app";
          program = toString (
            wslPkgs.writeShellScript "flake-update" ''
              set -e
              cd ~/.config/nix-config
              echo "==> Updating flake.lock..."
              nix flake update
              echo "==> Done! Run 'nix run .#switch' to apply."
            ''
          );
        };

        fmt = {
          type = "app";
          program = toString (
            wslPkgs.writeShellScript "treefmt-wrapper" ''
              exec ${wslTreefmtEval.config.build.wrapper}/bin/treefmt "$@"
            ''
          );
        };
      };

      # ===========================================================
      # Pi extension packages (両 system)
      # ===========================================================
      packages = {
        ${darwinSystem} =
          let
            extensions = import ./pkgs/pi-extensions {
              pkgs = darwinPkgs;
              agentPiSrc = agent-pi;
            };
          in
          {
            pi-agent-pi = extensions.agentPi;
            pi-hunk = extensions.piHunk;
            plannotator-pi-extension = extensions.plannotator;
            pi-context-view = extensions.contextView;
            pi-claude-auth = extensions.claudeAuth;
          };
        ${wslSystem} =
          let
            extensions = import ./pkgs/pi-extensions {
              pkgs = wslPkgs;
              agentPiSrc = agent-pi;
            };
          in
          {
            pi-agent-pi = extensions.agentPi;
            pi-hunk = extensions.piHunk;
            plannotator-pi-extension = extensions.plannotator;
            pi-context-view = extensions.contextView;
            pi-claude-auth = extensions.claudeAuth;
          };
      };

      # ===========================================================
      # formatter / checks / devShells (両 system)
      # ===========================================================
      formatter = {
        ${darwinSystem} = darwinTreefmtEval.config.build.wrapper;
        ${wslSystem} = wslTreefmtEval.config.build.wrapper;
      };

      checks = {
        ${darwinSystem} = {
          formatting = darwinTreefmtEval.config.build.check self;
          pre-commit = darwinPreCommitCheck;
        };
        ${wslSystem} = {
          formatting = wslTreefmtEval.config.build.check self;
          pre-commit = wslPreCommitCheck;
        };
      };

      devShells = {
        ${darwinSystem}.default = darwinPkgs.mkShell {
          inherit (darwinPreCommitCheck) shellHook;
        };
        ${wslSystem}.default = wslPkgs.mkShell {
          inherit (wslPreCommitCheck) shellHook;
        };
      };
    };
}
