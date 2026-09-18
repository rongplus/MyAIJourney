import pygame
import sys

# Initialize Pygame
pygame.init()

# Set up some constants
WIDTH = 800
HEIGHT = 600
PLAYER_SIZE = 50
PLAYER_SPEED = 5
ENEMY_SIZE = 30
ENEMY_SPEED = 3
POWERUP_SIZE = 20
POWERUP_SPEED = 2

# Set up the player
player = pygame.Rect(WIDTH/2, HEIGHT/2, PLAYER_SIZE, PLAYER_SIZE)
player_SPEED = 0

# Set up the enemies
enemies = [
    pygame.Rect(WIDTH/2 + i*50, HEIGHT/2, ENEMY_SIZE, ENEMY_SIZE)
    for i in range(10)
]

# Set up the powerups
powerups = [
    pygame.Rect(WIDTH/2 + i*50, HEIGHT/2, POWERUP_SIZE, POWERUP_SIZE)
    for i in range(5)
]

# Main game loop
while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                player.x -= player_SPEED
            elif event.key == pygame.K_RIGHT:
                player.x += player_SPEED
            elif event.key == pygame.K_UP:
                player.y -= player_SPEED
            elif event.key == pygame.K_DOWN:
                player.y += player_SPEED
            elif event.key == pygame.K_SPACE:
                # Shoot the enemies

    # Update the enemies
    for enemy in enemies:
        enemy.x += ENEMY_SPEED
        if enemy.x > WIDTH:
            enemy.x = 0

    # Check for collisions with enemies
    for enemy in enemies:
        if player.colliderect(enemy):
            # Handle collision with an enemy

    # Update the powerups
    for powerup in powerups:
        powerup.x += POWERUP_SPEED
        if powerup.x > WIDTH:
            powerup.x = 0

    # Check for collisions with powerups
    for powerup in powerups:
        if player.colliderect(powerup):
            # Handle collision with a powerup

    # Draw everything
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(。Retro Shooter、)
    pygame.draw.rect(screen, (255, 0, 0), player)
    for enemy in enemies:
        pygame.draw.rect(screen, (0, 0, 255), enemy)
    for powerup in powerups:
        pygame.draw.rect(screen, (0, 255, 0), powerup)
    pygame.display.flip()
