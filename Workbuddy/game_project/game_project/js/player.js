<script>
  class Player {
    constructor() {
      this.x = 100;
      this.y = 100;
      this.health = 100;
      this.gold = 0;
      this.exp = 0;
      this.score = 0;
    }

    attack(enemy) {
      enemy.health -= 10;
    }

    move(dx, dy) {
      this.x += dx;
      this.y += dy;
    }

    buy_upgrade(upgrade) {
      if (this.gold >= upgrade.cost) {
        this.gold -= upgrade.cost;
        // Upgrade logic here
      }
    }
  }
</script>