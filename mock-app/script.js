// Basic interaction script for the mock app
document.addEventListener('DOMContentLoaded', () => {
    const addToCartButtons = document.querySelectorAll('.add-to-cart');
    const cartCountElement = document.querySelector('.cart-count');
    
    let cartCount = 2; // Initial mock count
    
    addToCartButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            // Simple animation
            const originalText = button.textContent;
            button.textContent = 'Added!';
            button.style.backgroundColor = '#10b981'; // Green
            
            // Update cart
            cartCount++;
            cartCountElement.textContent = cartCount;
            
            // Reset button
            setTimeout(() => {
                button.textContent = originalText;
                button.style.backgroundColor = ''; // Revert to css default
            }, 1000);
        });
    });
});
