<script>
  class Enemy {
    constructor() {
      this.x = 200;
      this.y = 200;
      this.health = 50;
      this.attack = 10;
    }

    attack(player) {
      player.health -= this.attack;
    }

    move(dx, dy) {
      this.x += dx;
      this.y += dy;
    }
  }
</script>